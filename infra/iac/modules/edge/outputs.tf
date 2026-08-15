output "waf_web_acl_arn" {
  value = aws_wafv2_web_acl.this.arn
}

output "application_fqdn" {
  value = aws_route53_record.app.fqdn
}
