"""Simple NLB implementation with iptables forwarding."""
import logging
import subprocess
import uuid
from datetime import datetime
from typing import List

from localstack.aws.api import RequestContext
from localstack.aws.api.elbv2 import (
    ElasticLoadBalancingV2Api,
    LoadBalancerNotFoundException,
    TargetGroupNotFoundException,
    DuplicateLoadBalancerNameException,
)
from localstack.services.elbv2.models import (
    elbv2_stores,
    ELBv2Store,
    LoadBalancerState,
    TargetGroupState,
    ListenerState,
    Target,
)

LOG = logging.getLogger(__name__)

# Fixed target IP for all forwarding rules
TARGET_IP = "172.32.0.254"


class ELBv2Provider(ElasticLoadBalancingV2Api):
    """
    Minimal NLB implementation that uses iptables for actual traffic forwarding.
    All traffic is forwarded to TARGET_IP (172.32.0.254).
    """

    @staticmethod
    def get_store(account_id: str, region_name: str) -> ELBv2Store:
        return elbv2_stores[account_id][region_name]

    # ================== IPTABLES HELPERS ==================

    def _add_iptables_rule(self, listen_port: int, target_port: int) -> bool:
        """Add DNAT rule to forward traffic from listen_port to TARGET_IP:target_port."""
        try:
            # PREROUTING rule for external traffic
            cmd = [
                "iptables", "-t", "nat", "-A", "PREROUTING",
                "-p", "tcp", "--dport", str(listen_port),
                "-j", "DNAT", "--to-destination", f"{TARGET_IP}:{target_port}"
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            
            # OUTPUT rule for local traffic (from within container)
            cmd_output = [
                "iptables", "-t", "nat", "-A", "OUTPUT",
                "-p", "tcp", "--dport", str(listen_port),
                "-j", "DNAT", "--to-destination", f"{TARGET_IP}:{target_port}"
            ]
            subprocess.run(cmd_output, check=True, capture_output=True)
            
            LOG.info(f"Added iptables rule: :{listen_port} -> {TARGET_IP}:{target_port}")
            return True
        except subprocess.CalledProcessError as e:
            LOG.error(f"Failed to add iptables rule: {e.stderr.decode() if e.stderr else e}")
            return False

    def _remove_iptables_rule(self, listen_port: int, target_port: int) -> bool:
        """Remove DNAT rule."""
        try:
            cmd = [
                "iptables", "-t", "nat", "-D", "PREROUTING",
                "-p", "tcp", "--dport", str(listen_port),
                "-j", "DNAT", "--to-destination", f"{TARGET_IP}:{target_port}"
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            
            cmd_output = [
                "iptables", "-t", "nat", "-D", "OUTPUT",
                "-p", "tcp", "--dport", str(listen_port),
                "-j", "DNAT", "--to-destination", f"{TARGET_IP}:{target_port}"
            ]
            subprocess.run(cmd_output, check=True, capture_output=True)
            
            LOG.info(f"Removed iptables rule: :{listen_port} -> {TARGET_IP}:{target_port}")
            return True
        except subprocess.CalledProcessError as e:
            LOG.warning(f"Failed to remove iptables rule: {e.stderr.decode() if e.stderr else e}")
            return False

    def _sync_iptables_for_listener(self, store: ELBv2Store, listener: ListenerState):
        """Sync iptables rules based on listener's target group."""
        for action in listener.default_actions:
            if action.get("Type") == "forward":
                tg_arn = action.get("TargetGroupArn")
                tg = store.target_groups.get(tg_arn)
                if tg:
                    for target in tg.targets:
                        self._add_iptables_rule(listener.port, target.port)
                        store.iptables_rules[(listener.port, target.port)] = listener.arn

    # ================== LOAD BALANCER OPERATIONS ==================

    def create_load_balancer(
        self,
        context: RequestContext,
        name: str,
        subnets: List[str] = None,
        type: str = "network",
        scheme: str = "internet-facing",
        ip_address_type: str = "ipv4",
        tags: List[dict] = None,
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        # Check for duplicate name
        for lb in store.load_balancers.values():
            if lb.name == name:
                raise DuplicateLoadBalancerNameException(f"Load balancer '{name}' already exists")
        
        lb_id = str(uuid.uuid4())[:8]
        arn = f"arn:aws:elasticloadbalancing:{context.region}:{context.account_id}:loadbalancer/net/{name}/{lb_id}"
        dns_name = f"{name}-{lb_id}.elb.{context.region}.localhost.localstack.cloud"
        
        lb = LoadBalancerState(
            arn=arn,
            dns_name=dns_name,
            name=name,
            scheme=scheme,
            vpc_id=kwargs.get("vpc_id", "vpc-12345678"),
            lb_type=type,
            ip_address_type=ip_address_type,
            created_time=datetime.utcnow().isoformat(),
        )
        store.load_balancers[arn] = lb
        
        LOG.info(f"Created NLB: {name} ({arn})")
        
        return {
            "LoadBalancers": [{
                "LoadBalancerArn": arn,
                "DNSName": dns_name,
                "LoadBalancerName": name,
                "Scheme": scheme,
                "VpcId": lb.vpc_id,
                "State": {"Code": "active"},
                "Type": type,
                "IpAddressType": ip_address_type,
                "CreatedTime": lb.created_time,
            }]
        }

    def delete_load_balancer(
        self,
        context: RequestContext,
        load_balancer_arn: str,
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        if load_balancer_arn not in store.load_balancers:
            raise LoadBalancerNotFoundException(f"Load balancer '{load_balancer_arn}' not found")
        
        lb = store.load_balancers[load_balancer_arn]
        
        # Remove all listeners and their iptables rules
        for listener_arn in list(lb.listeners.keys()):
            self.delete_listener(context, listener_arn=listener_arn)
        
        del store.load_balancers[load_balancer_arn]
        LOG.info(f"Deleted NLB: {load_balancer_arn}")
        
        return {}

    def describe_load_balancers(
        self,
        context: RequestContext,
        load_balancer_arns: List[str] = None,
        names: List[str] = None,
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        results = []
        for arn, lb in store.load_balancers.items():
            if load_balancer_arns and arn not in load_balancer_arns:
                continue
            if names and lb.name not in names:
                continue
            results.append({
                "LoadBalancerArn": arn,
                "DNSName": lb.dns_name,
                "LoadBalancerName": lb.name,
                "Scheme": lb.scheme,
                "VpcId": lb.vpc_id,
                "State": {"Code": "active"},
                "Type": lb.lb_type,
                "IpAddressType": lb.ip_address_type,
                "CreatedTime": lb.created_time,
            })
        
        return {"LoadBalancers": results}

    # ================== TARGET GROUP OPERATIONS ==================

    def create_target_group(
        self,
        context: RequestContext,
        name: str,
        protocol: str = "TCP",
        port: int = 80,
        vpc_id: str = None,
        target_type: str = "ip",
        health_check_protocol: str = "TCP",
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        tg_id = str(uuid.uuid4())[:8]
        arn = f"arn:aws:elasticloadbalancing:{context.region}:{context.account_id}:targetgroup/{name}/{tg_id}"
        
        tg = TargetGroupState(
            arn=arn,
            name=name,
            protocol=protocol,
            port=port,
            vpc_id=vpc_id or "vpc-12345678",
            target_type=target_type,
            health_check_protocol=health_check_protocol,
            health_check_port=str(port),
        )
        store.target_groups[arn] = tg
        
        LOG.info(f"Created target group: {name} ({arn})")
        
        return {
            "TargetGroups": [{
                "TargetGroupArn": arn,
                "TargetGroupName": name,
                "Protocol": protocol,
                "Port": port,
                "VpcId": tg.vpc_id,
                "HealthCheckProtocol": health_check_protocol,
                "HealthCheckPort": str(port),
                "TargetType": target_type,
                "LoadBalancerArns": [],
            }]
        }

    def delete_target_group(
        self,
        context: RequestContext,
        target_group_arn: str,
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        if target_group_arn not in store.target_groups:
            raise TargetGroupNotFoundException(f"Target group '{target_group_arn}' not found")
        
        del store.target_groups[target_group_arn]
        LOG.info(f"Deleted target group: {target_group_arn}")
        
        return {}

    def describe_target_groups(
        self,
        context: RequestContext,
        target_group_arns: List[str] = None,
        names: List[str] = None,
        load_balancer_arn: str = None,
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        results = []
        for arn, tg in store.target_groups.items():
            if target_group_arns and arn not in target_group_arns:
                continue
            if names and tg.name not in names:
                continue
            if load_balancer_arn and load_balancer_arn not in tg.load_balancer_arns:
                continue
            results.append({
                "TargetGroupArn": arn,
                "TargetGroupName": tg.name,
                "Protocol": tg.protocol,
                "Port": tg.port,
                "VpcId": tg.vpc_id,
                "HealthCheckProtocol": tg.health_check_protocol,
                "HealthCheckPort": tg.health_check_port,
                "TargetType": tg.target_type,
                "LoadBalancerArns": tg.load_balancer_arns,
            })
        
        return {"TargetGroups": results}

    def register_targets(
        self,
        context: RequestContext,
        target_group_arn: str,
        targets: List[dict],
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        if target_group_arn not in store.target_groups:
            raise TargetGroupNotFoundException(f"Target group '{target_group_arn}' not found")
        
        tg = store.target_groups[target_group_arn]
        
        for t in targets:
            target = Target(
                id=t["Id"],  # Stored but not used for iptables - always use TARGET_IP
                port=t.get("Port", tg.port),
                availability_zone=t.get("AvailabilityZone", ""),
            )
            tg.targets.append(target)
            LOG.info(f"Registered target {target.id}:{target.port} to {target_group_arn} (will forward to {TARGET_IP}:{target.port})")
            
            # Add iptables rules for any listeners using this target group
            for listener in store.listeners.values():
                for action in listener.default_actions:
                    if action.get("Type") == "forward" and action.get("TargetGroupArn") == target_group_arn:
                        self._add_iptables_rule(listener.port, target.port)
                        store.iptables_rules[(listener.port, target.port)] = listener.arn
        
        return {}

    def deregister_targets(
        self,
        context: RequestContext,
        target_group_arn: str,
        targets: List[dict],
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        if target_group_arn not in store.target_groups:
            raise TargetGroupNotFoundException(f"Target group '{target_group_arn}' not found")
        
        tg = store.target_groups[target_group_arn]
        
        for t in targets:
            target_id = t["Id"]
            target_port = t.get("Port", tg.port)
            
            # Remove from target group
            tg.targets = [x for x in tg.targets if not (x.id == target_id and x.port == target_port)]
            
            # Remove iptables rules
            for listener in store.listeners.values():
                for action in listener.default_actions:
                    if action.get("Type") == "forward" and action.get("TargetGroupArn") == target_group_arn:
                        self._remove_iptables_rule(listener.port, target_port)
                        store.iptables_rules.pop((listener.port, target_port), None)
            
            LOG.info(f"Deregistered target {target_id}:{target_port} from {target_group_arn}")
        
        return {}

    # ================== LISTENER OPERATIONS ==================

    def create_listener(
        self,
        context: RequestContext,
        load_balancer_arn: str,
        protocol: str,
        port: int,
        default_actions: List[dict],
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        if load_balancer_arn not in store.load_balancers:
            raise LoadBalancerNotFoundException(f"Load balancer '{load_balancer_arn}' not found")
        
        lb = store.load_balancers[load_balancer_arn]
        
        listener_id = str(uuid.uuid4())[:8]
        arn = f"{load_balancer_arn}/listener/{listener_id}"
        
        listener = ListenerState(
            arn=arn,
            load_balancer_arn=load_balancer_arn,
            port=port,
            protocol=protocol,
            default_actions=default_actions,
        )
        store.listeners[arn] = listener
        lb.listeners[arn] = listener
        
        # Link target group to load balancer
        for action in default_actions:
            if action.get("Type") == "forward":
                tg_arn = action.get("TargetGroupArn")
                if tg_arn in store.target_groups:
                    tg = store.target_groups[tg_arn]
                    if load_balancer_arn not in tg.load_balancer_arns:
                        tg.load_balancer_arns.append(load_balancer_arn)
        
        # Set up iptables rules for existing targets
        self._sync_iptables_for_listener(store, listener)
        
        LOG.info(f"Created listener on port {port} for {load_balancer_arn}")
        
        return {
            "Listeners": [{
                "ListenerArn": arn,
                "LoadBalancerArn": load_balancer_arn,
                "Port": port,
                "Protocol": protocol,
                "DefaultActions": default_actions,
            }]
        }

    def delete_listener(
        self,
        context: RequestContext,
        listener_arn: str,
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        if listener_arn not in store.listeners:
            return {}  # AWS doesn't error on missing listener
        
        listener = store.listeners[listener_arn]
        
        # Remove iptables rules
        for action in listener.default_actions:
            if action.get("Type") == "forward":
                tg_arn = action.get("TargetGroupArn")
                tg = store.target_groups.get(tg_arn)
                if tg:
                    for target in tg.targets:
                        self._remove_iptables_rule(listener.port, target.port)
                        store.iptables_rules.pop((listener.port, target.port), None)
        
        # Remove from load balancer
        if listener.load_balancer_arn in store.load_balancers:
            lb = store.load_balancers[listener.load_balancer_arn]
            lb.listeners.pop(listener_arn, None)
        
        del store.listeners[listener_arn]
        LOG.info(f"Deleted listener: {listener_arn}")
        
        return {}

    def describe_listeners(
        self,
        context: RequestContext,
        load_balancer_arn: str = None,
        listener_arns: List[str] = None,
        **kwargs
    ) -> dict:
        store = self.get_store(context.account_id, context.region)
        
        results = []
        for arn, listener in store.listeners.items():
            if listener_arns and arn not in listener_arns:
                continue
            if load_balancer_arn and listener.load_balancer_arn != load_balancer_arn:
                continue
            results.append({
                "ListenerArn": arn,
                "LoadBalancerArn": listener.load_balancer_arn,
                "Port": listener.port,
                "Protocol": listener.protocol,
                "DefaultActions": listener.default_actions,
            })
        
        return {"Listeners": results}
