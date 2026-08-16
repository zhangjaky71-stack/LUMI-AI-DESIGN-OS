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
  sandbox_interface_endpoint_services = toset([
    "ecr.api",
    "ecr.dkr",
    "logs",
    "secretsmanager",
    "kms",
  ])
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
    Tier = "data-isolated"
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

# Data/isolated subnets deliberately have NO Internet/NAT default route. Sandbox
# runtime tasks use these subnets in production/staging so arbitrary egress has no
# route even if an application bug attempts it.
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

resource "aws_security_group" "app" {
  name        = "${local.name}-app"
  description = "Private ECS/Fargate application tasks."
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

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name}-app-sg" })
}

resource "aws_security_group" "sandbox" {
  name        = "${local.name}-sandbox"
  description = "Sandbox runtime: VPC-local traffic plus S3 endpoint only; no Internet egress."
  vpc_id      = aws_vpc.this.id

  # Stateful target security groups still decide whether a VPC-local destination
  # accepts traffic. Postgres intentionally does not trust this security group.
  egress {
    description = "VPC-local dependencies and interface endpoints"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description     = "S3 through the VPC gateway endpoint"
    protocol        = "tcp"
    from_port       = 443
    to_port         = 443
    prefix_list_ids = [data.aws_prefix_list.s3.id]
  }

  tags = merge(local.tags, { Name = "${local.name}-sandbox-sg" })
}

resource "aws_security_group" "sandbox_endpoints" {
  name        = "${local.name}-sandbox-endpoints"
  description = "Private AWS interface endpoints reachable only from sandbox runtime."
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "Sandbox HTTPS to AWS private endpoints"
    protocol        = "tcp"
    from_port       = 443
    to_port         = 443
    security_groups = [aws_security_group.sandbox.id]
  }

  tags = merge(local.tags, { Name = "${local.name}-sandbox-endpoints-sg" })
}

resource "aws_vpc_endpoint" "sandbox_interface" {
  for_each = local.sandbox_interface_endpoint_services

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [for az in var.availability_zones : aws_subnet.data[az].id]
  security_group_ids  = [aws_security_group.sandbox_endpoints.id]
  private_dns_enabled = true

  tags = merge(local.tags, {
    Name    = "${local.name}-${replace(each.value, ".", "-")}-endpoint"
    Purpose = "sandbox-no-internet"
  })
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for az in var.availability_zones : aws_route_table.data[az].id]

  tags = merge(local.tags, {
    Name    = "${local.name}-s3-endpoint"
    Purpose = "sandbox-no-internet"
  })
}
