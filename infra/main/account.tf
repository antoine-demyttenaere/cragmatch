# Snapshots and any later volume are encrypted too, even if a resource forgets to ask.
resource "aws_ebs_encryption_by_default" "this" {
  enabled = true
}

# Ticket 026 serves the site from a private bucket behind CloudFront, so nothing needs a public bucket.
resource "aws_s3_account_public_access_block" "this" {
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
