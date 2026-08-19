# Private service-to-service control planes are reachable only through Cloud Map/VPC DNS.
# The public ALB must reject these paths before the catch-all API forwarding rule.
resource "aws_lb_listener_rule" "deny_internal_paths" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 1

  action {
    type = "fixed-response"

    fixed_response {
      content_type = "application/json"
      message_body = "{\"detail\":\"not found\"}"
      status_code  = "404"
    }
  }

  condition {
    path_pattern {
      values = ["/internal", "/internal/*"]
    }
  }
}
