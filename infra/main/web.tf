resource "aws_s3_bucket" "web" {
  bucket = "cragmatch-web-${data.aws_caller_identity.current.account_id}-${var.region}"

  # Every object can be rebuilt from git, and destroy must not get stuck on a full bucket.
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket = aws_s3_bucket.web.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "web" {
  bucket = aws_s3_bucket.web.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# SSE-KMS would need a key policy for CloudFront; SSE-S3 needs nothing.
resource "aws_s3_bucket_server_side_encryption_configuration" "web" {
  bucket = aws_s3_bucket.web.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# No versioning: a rollback is a rebuild from git (runbook), and old index.html versions would only cost.

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "cragmatch-web"
  description                       = "CloudFront signs its requests to the private site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# release/* stays unreadable to visitors. There is no ListBucket, so a missing key is a 403, which the
# distribution's error response turns into the app.
resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "ReadSiteThroughTheWebDistribution"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource = [
          "${aws_s3_bucket.web.arn}/index.html",
          "${aws_s3_bucket.web.arn}/assets/*",
        ]
        Condition = {
          StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.web.arn }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.web.arn,
          "${aws_s3_bucket.web.arn}/*",
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      },
    ]
  })

  # The public access block and the policy are both bucket-level writes (see the state bucket).
  depends_on = [aws_s3_bucket_public_access_block.web]
}

locals {
  web_csp = join("; ", [
    "default-src 'self'",
    "script-src 'self'",
    # No inline styles or style attributes exist in web/src, so 'unsafe-inline' is not needed.
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    # Exactly the API's origin: even injected script could not talk to another host. A future
    # external call (maps, analytics) must add itself here.
    "connect-src 'self' https://${aws_cloudfront_distribution.api.domain_name}",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ])
}

# Our own policy: the managed SecurityHeadersPolicy has no CSP and uses X-Frame-Options SAMEORIGIN.
resource "aws_cloudfront_response_headers_policy" "web" {
  name    = "cragmatch-web-security"
  comment = "Security headers for the CragMatch site"

  security_headers_config {
    # No includeSubDomains (the parent domain is cloudfront.net) and no preload.
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = false
      preload                    = false
      override                   = true
    }

    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    # The share link's ?group=CODE then never leaves in a Referer, not even to Airbnb or Booking.
    referrer_policy {
      referrer_policy = "no-referrer"
      override        = true
    }

    content_security_policy {
      content_security_policy = local.web_csp
      override                = true
    }
  }
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

# The site's own distribution, separate from aws_cloudfront_distribution.api (025), which must stay
# API-only. Cache rules for each file type are set by infra/web/publish-web.sh as object metadata.
resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  comment             = "CragMatch web"
  default_root_object = "index.html"

  # Static files with no rate limit, so there is no reason to refuse IPv6 (unlike the API).
  is_ipv6_enabled = true
  http_version    = "http2and3"
  price_class     = "PriceClass_100"

  origin {
    origin_id                = "site"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  default_cache_behavior {
    target_origin_id       = "site"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD"]
    cached_methods  = ["GET", "HEAD"]
    compress        = true

    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.web.id
  }

  # S3 answers 403 (not 404) for a missing key because CloudFront has no ListBucket. Both open the
  # app. TTL 0 so a new index.html also reaches mistyped paths at once.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # The default *.cloudfront.net certificate: no custom domain.
  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Read by the Deploy workflow.
resource "aws_ssm_parameter" "deploy_web_bucket" {
  name  = "/cragmatch/deploy/web_bucket"
  type  = "String"
  value = aws_s3_bucket.web.id
}

resource "aws_ssm_parameter" "deploy_web_distribution_id" {
  name  = "/cragmatch/deploy/web_distribution_id"
  type  = "String"
  value = aws_cloudfront_distribution.web.id
}

resource "aws_ssm_parameter" "deploy_web_url" {
  name  = "/cragmatch/deploy/web_url"
  type  = "String"
  value = "https://${aws_cloudfront_distribution.web.domain_name}"
}

# Separate from 025's policy, so each ticket's test pins its own permissions.
resource "aws_iam_role_policy" "github_deploy_web" {
  name = "cragmatch-deploy-web"
  role = aws_iam_role.github_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListSite"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.web.arn
      },
      {
        Sid    = "WriteSite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = "${aws_s3_bucket.web.arn}/*"
      },
      {
        # The script reads the last release record and nothing else.
        Sid      = "ReadRelease"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.web.arn}/release/*"
      },
      {
        # GetInvalidation is what "wait invalidation-completed" calls.
        Sid    = "InvalidateSite"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateInvalidation",
          "cloudfront:GetInvalidation",
        ]
        Resource = aws_cloudfront_distribution.web.arn
      },
    ]
  })
}
