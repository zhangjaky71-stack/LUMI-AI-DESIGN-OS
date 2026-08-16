data "aws_caller_identity" "current" {}

resource "aws_sns_topic" "deployment_alerts" {
  name              = "${local.name}-deployment-alerts"
  kms_master_key_id = "alias/aws/sns"
  tags              = local.tags
}

resource "aws_sqs_queue" "deployment_alert_evidence" {
  name                      = "${local.name}-deployment-alert-evidence"
  message_retention_seconds = 1209600
  visibility_timeout_seconds = 60
  sqs_managed_sse_enabled   = true
  tags                      = local.tags
}

data "aws_iam_policy_document" "deployment_alert_topic" {
  statement {
    sid     = "CloudWatchAlarmPublish"
    effect  = "Allow"
    actions = ["sns:Publish"]
    resources = [aws_sns_topic.deployment_alerts.arn]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  statement {
    sid     = "EventBridgePublish"
    effect  = "Allow"
    actions = ["sns:Publish"]
    resources = [aws_sns_topic.deployment_alerts.arn]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "deployment_alerts" {
  arn    = aws_sns_topic.deployment_alerts.arn
  policy = data.aws_iam_policy_document.deployment_alert_topic.json
}

data "aws_iam_policy_document" "deployment_alert_evidence" {
  statement {
    sid       = "SnsDelivery"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.deployment_alert_evidence.arn]

    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_sns_topic.deployment_alerts.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "deployment_alert_evidence" {
  queue_url = aws_sqs_queue.deployment_alert_evidence.id
  policy    = data.aws_iam_policy_document.deployment_alert_evidence.json
}

resource "aws_sns_topic_subscription" "deployment_alert_evidence" {
  topic_arn            = aws_sns_topic.deployment_alerts.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.deployment_alert_evidence.arn
  raw_message_delivery = false

  depends_on = [aws_sqs_queue_policy.deployment_alert_evidence]
}

resource "aws_cloudwatch_composite_alarm" "public_deployment" {
  for_each = local.public_services

  alarm_name        = "${local.name}-${each.key}-deployment"
  alarm_description = "Notify operators whenever an ECS public canary rollback alarm fires."
  actions_enabled   = true
  alarm_actions     = [aws_sns_topic.deployment_alerts.arn]
  ok_actions        = [aws_sns_topic.deployment_alerts.arn]
  alarm_rule = format(
    "ALARM(\"%s\") OR ALARM(\"%s\")",
    aws_cloudwatch_metric_alarm.public_canary_5xx[each.key].alarm_name,
    aws_cloudwatch_metric_alarm.public_canary_unhealthy[each.key].alarm_name,
  )

  tags = local.tags
}

resource "aws_cloudwatch_event_rule" "ecs_deployment_failure" {
  name        = "${local.name}-ecs-deployment-failure"
  description = "Route ECS deployment failures, including non-public circuit-breaker rollbacks, to the deployment alert topic."

  event_pattern = jsonencode({
    source        = ["aws.ecs"]
    "detail-type" = ["ECS Deployment State Change"]
    detail = {
      eventName = ["SERVICE_DEPLOYMENT_FAILED"]
    }
  })

  tags = local.tags
}

resource "aws_cloudwatch_event_target" "ecs_deployment_failure" {
  rule = aws_cloudwatch_event_rule.ecs_deployment_failure.name
  arn  = aws_sns_topic.deployment_alerts.arn

  depends_on = [aws_sns_topic_policy.deployment_alerts]
}
