output "kms_key_arn" {
  value = aws_kms_key.this.arn
}

output "bucket_arns" {
  value = { for name, bucket in aws_s3_bucket.this : name => bucket.arn }
}

output "bucket_names" {
  value = { for name, bucket in aws_s3_bucket.this : name => bucket.bucket }
}
