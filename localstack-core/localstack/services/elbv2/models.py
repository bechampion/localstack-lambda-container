"""State storage for ELBv2 NLB implementation."""
from typing import Dict, List
from dataclasses import dataclass, field
from localstack.services.stores import AccountRegionBundle, BaseStore, LocalAttribute


@dataclass
class Target:
    id: str  # IP address or instance ID (stored but not used for iptables)
    port: int
    availability_zone: str = ""


@dataclass 
class TargetGroupState:
    arn: str
    name: str
    protocol: str
    port: int
    vpc_id: str
    target_type: str
    health_check_protocol: str
    health_check_port: str
    targets: List[Target] = field(default_factory=list)
    load_balancer_arns: List[str] = field(default_factory=list)


@dataclass
class ListenerState:
    arn: str
    load_balancer_arn: str
    port: int
    protocol: str
    default_actions: List[dict] = field(default_factory=list)


@dataclass
class LoadBalancerState:
    arn: str
    dns_name: str
    name: str
    scheme: str
    vpc_id: str
    lb_type: str
    ip_address_type: str
    created_time: str
    listeners: Dict[str, ListenerState] = field(default_factory=dict)


class ELBv2Store(BaseStore):
    # Maps load balancer ARN -> LoadBalancerState
    load_balancers: Dict[str, LoadBalancerState] = LocalAttribute(default=dict)
    
    # Maps target group ARN -> TargetGroupState
    target_groups: Dict[str, TargetGroupState] = LocalAttribute(default=dict)
    
    # Maps listener ARN -> ListenerState  
    listeners: Dict[str, ListenerState] = LocalAttribute(default=dict)
    
    # Track iptables rules: (listen_port, target_port) -> listener_arn
    iptables_rules: Dict[tuple, str] = LocalAttribute(default=dict)


elbv2_stores = AccountRegionBundle("elbv2", ELBv2Store)
