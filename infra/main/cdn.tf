data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

# The API's own distribution. Ticket 026's site is a SEPARATE distribution: do not add behaviours
# for it here, so the API's lifecycle stays apart from the site's.
resource "aws_cloudfront_distribution" "api" {
  enabled = true
  comment = "CragMatch API"

  # Viewers come in over IPv4 so a client cannot dodge its per-address rate limit by cycling through
  # the many addresses of an IPv6 /64. IPv6-only phones still arrive through their carrier's NAT64.
  is_ipv6_enabled = false

  # Europe and North America edges are the cheapest and close enough for friends.
  price_class = "PriceClass_100"

  origin {
    origin_id = "host"
    # The Elastic IP's name stays the same when the host is replaced.
    domain_name = aws_eip.host.public_dns

    custom_origin_config {
      http_port  = 80
      https_port = 443
      # CloudFront refuses self-signed origin certificates and we have no domain for a public one.
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      # Claude answers can take tens of seconds; the default is 30.
      origin_read_timeout = 60
      # Below uvicorn's 5 s keep-alive, so CloudFront closes idle connections first and never reuses
      # one that uvicorn just closed (sporadic 502s otherwise).
      origin_keepalive_timeout = 4
    }

    # Every request was HTTPS at the viewer (see the viewer policy) and CloudFront strips a viewer's
    # own copy of this header. Redirects then point at https.
    custom_header {
      name  = "X-Forwarded-Proto"
      value = "https"
    }
  }

  default_cache_behavior {
    target_origin_id       = "host"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD"]
    compress        = false

    # Caches nothing, not even error codes, so a 503 during a deploy is never served stale.
    cache_policy_id = data.aws_cloudfront_cache_policy.caching_disabled.id
    # Forwards every header (Origin for CORS, Host so redirects keep the public name), query and cookie.
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
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
