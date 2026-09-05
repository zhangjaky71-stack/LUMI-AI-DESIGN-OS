output "repository_urls" {
  value = {
    for name, repository in aws_ecr_repository.runtime :
    name => repository.repository_url
  }
}

output "repository_arns" {
  value = {
    for name, repository in aws_ecr_repository.runtime :
    name => repository.arn
  }
}
