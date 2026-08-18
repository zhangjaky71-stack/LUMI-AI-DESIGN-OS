locals {
  name = "${var.project}-${var.environment}"
  azs = {
    for index, az in var.availability_zones : az => {
      public_cidr  = var.public_subnet_cidrs[index]
      private_cidr = var.private_subnet_cidrs[index]
      data_cidr    = var.data_subnet_cidrs[index]
    }
  }
  tags = merge(var.tags, {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

data "aws_region" "current" {}

data "aws_prefix_list" "s3" {
  name = "com.amazonaws.${data.aws_region.current.name}.s3"
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.tags, { Name = "${local.name}-vpc" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${local.name}-igw" })
}

resource "aws_subnet" "public" {
  for_each = local.azs

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = each.value.public_cidr
  map_public_ip_on_launch = false

  tags = merge(local.tags, {
    Name = "${local.name}-public-${each.key}"
    Tier = "public"
  })
}

resource "aws_subnet" "private" {
  for_each = local.azs

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = each.value.private_cidr
  map_public_ip_on_launch = false

  tags = merge(local.tags, {
    Name = "${local.name}-private-${each.key}"
    Tier = "private"
  })
}

resource "aws_subnet" "data" {
  for_each = local.azs

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = each.value.data_cidr
  map_public_ip_on_launch = false

  tags = merge(local.tags, {
    Name = "${local.name}-data-${each.key}"
    Tier = "data"
  })
}

resource "aws_eip" "nat" {
  for_each = local.azs
  domain   = "vpc"
  tags     = merge(local.tags, { Name = "${local.name}-nat-eip-${each.key}" })
}

resource "aws_nat_gateway" "this" {
  for_each = local.azs

  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id

  depends_on = [aws_internet_gateway.this]
  tags       = merge(local.tags, { Name = "${local.name}-nat-${each.key}" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = merge(local.tags, { Name = "${local.name}-public-rt" })
}

resource "aws_route_table_association" "public" {
  for_each = local.azs

  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  for_each = local.azs

  vpc_id = aws_vpc.this.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[each.key].id
  }
  tags = merge(local.tags, { Name = "${local.name}-private-rt-${each.key}" })
}

resource "aws_route_table_association" "private" {
  for_each = local.azs

  subnet_id      = aws_subnet.private[each.key].id
  route_table_id = aws_route_table.private[each.key].id
}

# Data subnets deliberately have no direct Internet default route.
resource "aws_route_table" "data" {
  for_each = local.azs

  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${local.name}-data-rt-${each.key}" })
}

resource "aws_route_table_association" "data" {
  for_each = local.azs

  subnet_id      = aws_subnet.data[each.key].id
  route_table_id = aws_route_table.data[each.key].id
}

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Public TLS ingress to the application load balancer only."
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTPS"
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name}-alb-sg" })
}

# Identity / ingress group shared by application tasks. It intentionally has no
# outbound rule; outbound capability is attached through an explicit egress SG.
resource "aws_security_group" "app" {
  name        = "${local.name}-app"
  description = "Private ECS/Fargate application task identity; egress is explicit."
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "ALB to LUMI API HTTP"
    protocol        = "tcp"
    from_port       = 8000
    to_port         = 8000
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description = "Service-to-service traffic within application security group"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    self        = true
  }

  tags = merge(local.tags, { Name = "${local.name}-app-sg" })
}

# General application services need provider/webhook/package egress. Keeping this
# permission in a separate SG means sandbox-runtime can omit it entirely.
resource "aws_security_group" "app_internet_egress" {
  name        = "${local.name}-app-internet-egress"
  description = "Explicit Internet egress capability for non-sandbox services."
  vpc_id      = aws_vpc.this.id

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name}-app-internet-egress-sg" })
}

# Production sandbox control-plane tasks may reach only private VPC services and
# the AWS-managed S3 prefix list. They cannot reach arbitrary Internet addresses
# even though the private subnet has a NAT route.
resource "aws_security_group" "sandbox_egress" {
  name        = "${local.name}-sandbox-egress"
  description = "Fail-closed sandbox control-plane egress: VPC internal plus S3 only."
  vpc_id      = aws_vpc.this.id

  egress {
    description = "Private VPC control plane and PrivateLink endpoints"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = [aws_vpc.this.cidr_block]
  }

  egress {
    description     = "S3 asset transport only"
    protocol        = "tcp"
    from_port       = 443
    to_port         = 443
    prefix_list_ids = [data.aws_prefix_list.s3.id]
  }

  tags = merge(local.tags, {
    Name             = "${local.name}-sandbox-egress-sg"
    EgressPolicy     = "deny-public-except-s3"
    SecurityBoundary = "sandbox"
  })
}

# Fargate execution traffic (ECR image metadata/layers, CloudWatch Logs and
# Secrets Manager) stays inside AWS PrivateLink rather than requiring public NAT.
resource "aws_security_group" "runtime_endpoints" {
  name        = "${local.name}-runtime-endpoints"
  description = "PrivateLink ingress from LUMI application task identities."
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "HTTPS from application task identity"
    protocol        = "tcp"
    from_port       = 443
    to_port         = 443
    security_groups = [aws_security_group.app.id]
  }

  tags = merge(local.tags, { Name = "${local.name}-runtime-endpoints-sg" })
}

resource "aws_vpc_endpoint" "runtime_interface" {
  for_each = toset([
    "ecr.api",
    "ecr.dkr",
    "logs",
    "secretsmanager",
  ])

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.value}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [for az in var.availability_zones : aws_subnet.private[az].id]
  security_group_ids  = [aws_security_group.runtime_endpoints.id]

  tags = merge(local.tags, {
    Name             = "${local.name}-${replace(each.value, ".", "-")}-endpoint"
    SecurityBoundary = "private-runtime"
  })
}
