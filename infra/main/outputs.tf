output "region" {
  description = "The region everything runs in."
  value       = var.region
}

output "vpc_id" {
  description = "The VPC."
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "The one public subnet."
  value       = aws_subnet.public.id
}

output "host_security_group_id" {
  description = "Security group of the host. Ticket 025 adds its only inbound rule."
  value       = aws_security_group.host.id
}

output "host_instance_id" {
  description = "Instance id of the host, for aws ssm start-session."
  value       = aws_instance.host.id
}

output "host_public_dns" {
  description = "Public DNS name of the host's Elastic IP."
  value       = aws_eip.host.public_dns
}

output "host_public_ip" {
  description = "The host's Elastic IP. Stable when the instance is replaced."
  value       = aws_eip.host.public_ip
}

output "docker_network" {
  description = "Name of the Docker network on the host."
  value       = "cragmatch"
}

output "db_host" {
  description = "Database host name on the Docker network."
  value       = "db"
}

output "db_name" {
  description = "Database name."
  value       = "cragmatch"
}

output "db_user" {
  description = "Database user."
  value       = "cragmatch"
}

output "db_password_parameter" {
  description = "Name of the SSM parameter that holds the database password (the name, not the value)."
  value       = aws_ssm_parameter.db_password.name
}

output "host_role_name" {
  description = "IAM role of the host. Ticket 025 attaches more permissions."
  value       = aws_iam_role.host.name
}

output "api_url" {
  description = "The API's public HTTPS address (no trailing slash)."
  value       = "https://${aws_cloudfront_distribution.api.domain_name}"
}

output "api_distribution_id" {
  description = "Id of the API CloudFront distribution."
  value       = aws_cloudfront_distribution.api.id
}

output "api_distribution_domain" {
  description = "The API distribution's *.cloudfront.net name."
  value       = aws_cloudfront_distribution.api.domain_name
}

output "ecr_repository_url" {
  description = "Registry address of the API image repository."
  value       = aws_ecr_repository.api.repository_url
}

output "deploy_document_name" {
  description = "Name of the SSM document that deploys an API image."
  value       = aws_ssm_document.deploy_api.name
}

output "api_log_group" {
  description = "CloudWatch log group of the API container."
  value       = aws_cloudwatch_log_group.api.name
}

output "github_deploy_role_arn" {
  description = "ARN of the role GitHub Actions assumes on main. Set it as the AWS_DEPLOY_ROLE_ARN repository variable."
  value       = aws_iam_role.github_deploy.arn
}
