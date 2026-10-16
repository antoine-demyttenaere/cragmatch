output "state_bucket" {
  description = "Name of the S3 bucket that holds the Terraform state of every stack."
  value       = aws_s3_bucket.state.bucket
}

output "backend_config" {
  description = "Contents for infra/backend.hcl, used as -backend-config by every stack."
  value       = "bucket = \"${aws_s3_bucket.state.bucket}\"\nregion = \"${var.region}\"\n"
}
