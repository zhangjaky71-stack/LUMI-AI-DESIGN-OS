# sandbox-runtime launches secretless child tasks through the ECS control-plane API.
# Keep that control traffic inside the VPC because sandbox-runtime intentionally
# does not receive the general Internet-egress security group.
resource "aws_vpc_endpoint" "sandbox_ecs_control" {
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.ecs"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [for az in var.availability_zones : aws_subnet.private[az].id]
  security_group_ids  = [aws_security_group.runtime_endpoints.id]

  tags = merge(local.tags, {
    Name             = "${local.name}-ecs-endpoint"
    SecurityBoundary = "sandbox-remote-control"
  })
}
