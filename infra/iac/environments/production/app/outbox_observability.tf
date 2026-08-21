locals {
  outbox_dispatcher_log_group = "/lumi/${local.environment}/outbox-dispatcher"
  outbox_dispatcher_metric_namespace = "LUMI/MediaDispatch"
  outbox_oldest_age_metric = "${local.project}-${local.environment}-OutboxOldestUnpublishedAgeSeconds"
  outbox_oldest_attempts_metric = "${local.project}-${local.environment}-OutboxOldestPublishAttempts"
}

resource "aws_cloudwatch_log_metric_filter" "outbox_oldest_unpublished_age" {
  name           = "${local.project}-${local.environment}-outbox-oldest-unpublished-age"
  log_group_name = local.outbox_dispatcher_log_group
  pattern        = "{ $.kind = \"lumi.outbox_dispatcher.health\" }"

  metric_transformation {
    name          = local.outbox_oldest_age_metric
    namespace     = local.outbox_dispatcher_metric_namespace
    value         = "$.oldest_unpublished_age_seconds"
    default_value = "0"
  }

  depends_on = [module.platform_app]
}

resource "aws_cloudwatch_log_metric_filter" "outbox_oldest_publish_attempts" {
  name           = "${local.project}-${local.environment}-outbox-oldest-publish-attempts"
  log_group_name = local.outbox_dispatcher_log_group
  pattern        = "{ $.kind = \"lumi.outbox_dispatcher.health\" }"

  metric_transformation {
    name          = local.outbox_oldest_attempts_metric
    namespace     = local.outbox_dispatcher_metric_namespace
    value         = "$.oldest_publish_attempts"
    default_value = "0"
  }

  depends_on = [module.platform_app]
}

resource "aws_cloudwatch_metric_alarm" "outbox_oldest_unpublished_age" {
  alarm_name          = "${local.project}-${local.environment}-outbox-stale"
  alarm_description   = "Outbox dispatcher has a canonical job dispatch row pending for at least five minutes."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = local.outbox_oldest_age_metric
  namespace           = local.outbox_dispatcher_metric_namespace
  period              = 60
  statistic           = "Maximum"
  threshold           = 300
  treat_missing_data  = "notBreaching"

  tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "terraform"
    ReleaseNode = "NODE-72"
  }
}

resource "aws_cloudwatch_metric_alarm" "outbox_oldest_publish_attempts" {
  alarm_name          = "${local.project}-${local.environment}-outbox-publish-retries"
  alarm_description   = "The oldest canonical job dispatch row has reached at least five publish attempts."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = local.outbox_oldest_attempts_metric
  namespace           = local.outbox_dispatcher_metric_namespace
  period              = 60
  statistic           = "Maximum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "terraform"
    ReleaseNode = "NODE-72"
  }
}
