"""Minimal ELBv2 API interface for NLB support."""
from typing import TypedDict, List
from localstack.aws.api.core import ServiceException, handler


# --- Exceptions ---
class LoadBalancerNotFoundException(ServiceException):
    code = "LoadBalancerNotFound"
    status_code = 400
    sender_fault = True


class TargetGroupNotFoundException(ServiceException):
    code = "TargetGroupNotFound"
    status_code = 400
    sender_fault = True


class DuplicateLoadBalancerNameException(ServiceException):
    code = "DuplicateLoadBalancerName"
    status_code = 400
    sender_fault = True


class ListenerNotFoundException(ServiceException):
    code = "ListenerNotFound"
    status_code = 400
    sender_fault = True


# --- Types ---
class Tag(TypedDict, total=False):
    Key: str
    Value: str


class TargetDescription(TypedDict, total=False):
    Id: str
    Port: int
    AvailabilityZone: str


class LoadBalancer(TypedDict, total=False):
    LoadBalancerArn: str
    DNSName: str
    LoadBalancerName: str
    Scheme: str
    VpcId: str
    State: dict
    Type: str
    IpAddressType: str
    CreatedTime: str


class TargetGroup(TypedDict, total=False):
    TargetGroupArn: str
    TargetGroupName: str
    Protocol: str
    Port: int
    VpcId: str
    HealthCheckProtocol: str
    HealthCheckPort: str
    TargetType: str
    LoadBalancerArns: List[str]


class Listener(TypedDict, total=False):
    ListenerArn: str
    LoadBalancerArn: str
    Port: int
    Protocol: str
    DefaultActions: List[dict]


# --- API Interface ---
class ElasticLoadBalancingV2Api:
    service = "elbv2"
    version = "2015-12-01"

    @handler("CreateLoadBalancer")
    def create_load_balancer(
        self, context, name: str, subnets: List[str] = None,
        type: str = "application", scheme: str = "internet-facing",
        ip_address_type: str = "ipv4", tags: List[Tag] = None, **kwargs
    ) -> dict:
        raise NotImplementedError

    @handler("DeleteLoadBalancer")
    def delete_load_balancer(self, context, load_balancer_arn: str, **kwargs) -> dict:
        raise NotImplementedError

    @handler("DescribeLoadBalancers")
    def describe_load_balancers(
        self, context, load_balancer_arns: List[str] = None,
        names: List[str] = None, **kwargs
    ) -> dict:
        raise NotImplementedError

    @handler("CreateTargetGroup")
    def create_target_group(
        self, context, name: str, protocol: str = "TCP", port: int = 80,
        vpc_id: str = None, target_type: str = "instance",
        health_check_protocol: str = "TCP", **kwargs
    ) -> dict:
        raise NotImplementedError

    @handler("DeleteTargetGroup")
    def delete_target_group(self, context, target_group_arn: str, **kwargs) -> dict:
        raise NotImplementedError

    @handler("DescribeTargetGroups")
    def describe_target_groups(
        self, context, target_group_arns: List[str] = None,
        names: List[str] = None, load_balancer_arn: str = None, **kwargs
    ) -> dict:
        raise NotImplementedError

    @handler("RegisterTargets")
    def register_targets(
        self, context, target_group_arn: str, targets: List[TargetDescription], **kwargs
    ) -> dict:
        raise NotImplementedError

    @handler("DeregisterTargets")
    def deregister_targets(
        self, context, target_group_arn: str, targets: List[TargetDescription], **kwargs
    ) -> dict:
        raise NotImplementedError

    @handler("CreateListener")
    def create_listener(
        self, context, load_balancer_arn: str, protocol: str, port: int,
        default_actions: List[dict], **kwargs
    ) -> dict:
        raise NotImplementedError

    @handler("DeleteListener")
    def delete_listener(self, context, listener_arn: str, **kwargs) -> dict:
        raise NotImplementedError

    @handler("DescribeListeners")
    def describe_listeners(
        self, context, load_balancer_arn: str = None,
        listener_arns: List[str] = None, **kwargs
    ) -> dict:
        raise NotImplementedError
