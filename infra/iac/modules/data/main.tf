locals {
  name = "${var.project}-${var.environment}"
  tags = merge(var.tags, {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_security_group" "postgres" {
  name        = "${local.name}-postgres"
  description = "PostgreSQL reachable only from LUMI application tasks."
  vpc_id      = var.vpc_id

  ingress {
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [var.app_security_group_id]
  }

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name}-postgres-sg" })
}

resource "aws_security_group" "redis" {
  name        = "${local.name}-redis"
  description = "Redis reachable from LUMI application and sandbox runtime tasks only."
  vpc_id      = var.vpc_id

  ingress {
    protocol = "tcp"
    from_port = 6379
    to_port   = 6379
    security_groups = [
      var.app_security_group_id,
      var.sandbox_security_group_id,
    ]
  }

  tags = merge(local.tags, { Name = "${local.name}-redis-sg" })
}

resource "aws_security_group" "rabbitmq" {
  name        = "${local.name}-rabbitmq"
  description = "RabbitMQ AMQPS reachable from LUMI application and sandbox runtime tasks only."
  vpc_id      = var.vpc_id

  ingress {
    protocol = "tcp"
    from_port = 5671
    to_port   = 5671
    security_groups = [
      var.app_security_group_id,
      var.sandbox_security_group_id,
    ]
  }

  tags = merge(local.tags, { Name = "${local.name}-rabbitmq-sg" })
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.name}-postgres"
  subnet_ids = var.data_subnet_ids
  tags       = merge(local.tags, { Name = "${local.name}-postgres-subnets" })
}

resource "aws_db_instance" "postgres" {
  identifier = "${local.name}-postgres"

  engine         = "postgres"
  engine_version = var.postgres_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage_gb
  max_allocated_storage = var.db_max_allocated_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  db_name                     = "lumi"
  username                    = "lumi_master"
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.postgres.id]
  port                   = 5432
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period = var.db_backup_retention_days
  backup_window           = "18:00-19:00"
  maintenance_window      = "sun:19:30-sun:20:30"
  copy_tags_to_snapshot   = true

  deletion_protection             = var.environment == "production"
  skip_final_snapshot             = var.environment != "production"
  final_snapshot_identifier       = var.environment == "production" ? "${local.name}-postgres-final" : null
  auto_minor_version_upgrade      = true
  performance_insights_enabled    = true
  performance_insights_kms_key_id = var.kms_key_arn

  tags = merge(local.tags, { Name = "${local.name}-postgres" })
}

resource "aws_elasticache_subnet_group" "this" {
  name       = "${local.name}-redis"
  subnet_ids = var.data_subnet_ids
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${local.name}-redis"
  description          = "${local.name} Redis cache/session coordination"

  engine         = "redis"
  engine_version = var.redis_engine_version
  node_type      = var.redis_node_type
  port           = 6379

  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = var.redis_auth_token
  kms_key_id                 = var.kms_key_arn

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.redis.id]

  snapshot_retention_limit = var.environment == "production" ? 7 : 1
  snapshot_window          = "17:00-18:00"
  maintenance_window       = "sun:20:30-sun:21:30"
  apply_immediately        = false

  tags = merge(local.tags, { Name = "${local.name}-redis" })
}

resource "aws_mq_broker" "rabbitmq" {
  broker_name = "${local.name}-rabbitmq"

  engine_type        = "RABBITMQ"
  engine_version     = var.rabbitmq_engine_version
  host_instance_type = var.rabbitmq_instance_type
  deployment_mode    = "CLUSTER_MULTI_AZ"

  publicly_accessible = false
  subnet_ids          = var.data_subnet_ids
  security_groups     = [aws_security_group.rabbitmq.id]

  encryption_options {
    use_aws_owned_key = false
    kms_key_id        = var.kms_key_arn
  }

  logs {
    general = true
  }

  user {
    username = var.rabbitmq_username
    password = var.rabbitmq_password
  }

  maintenance_window_start_time {
    day_of_week = "SUNDAY"
    time_of_day = "22:00"
    time_zone   = "UTC"
  }

  tags = merge(local.tags, { Name = "${local.name}-rabbitmq" })
}
