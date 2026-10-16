data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block = "10.42.0.0/16"

  # Ticket 025's CloudFront origin uses the host's public DNS name.
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "cragmatch" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "cragmatch" }
}

resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.42.1.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]

  # The only public address is the Elastic IP below; an automatic one would cost 3.65 USD more a month.
  map_public_ip_on_launch = false

  lifecycle {
    # If the first zone is ever impaired, names[0] becomes the second one. A changed zone would
    # replace the subnet, the host and the data volume (whose zone comes from this subnet), and
    # destroy the database. A zone change must be a deliberate migration, never an apply side effect.
    ignore_changes = [availability_zone]
  }

  tags = { Name = "cragmatch-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "cragmatch-public" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Adopts the VPC's default group with no rules, so nothing can use it by accident.
resource "aws_default_security_group" "default" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "cragmatch-default-unused" }
}

# There is deliberately no ingress rule: SSM (shell and port forwarding) needs only outbound
# traffic, and ticket 025 adds the one inbound rule (CloudFront only).
# There is also no NAT gateway (about 35 USD a month): the host reaches Claude, Voyage and the
# package repositories through its own public address.
resource "aws_security_group" "host" {
  name        = "cragmatch-host"
  description = "CragMatch host: no inbound rules, outbound HTTP and HTTPS only"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "cragmatch-host" }
}

resource "aws_vpc_security_group_egress_rule" "https_out" {
  security_group_id = aws_security_group.host.id
  description       = "HTTPS to the APIs, package repositories and SSM"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# The Debian and PGDG apt repositories used by the database image build are plain HTTP. apt
# checks package signatures, so HTTP is safe here. Switching apt to https would need
# ca-certificates, which would itself have to be installed over HTTP.
resource "aws_vpc_security_group_egress_rule" "http_out" {
  security_group_id = aws_security_group.host.id
  description       = "HTTP to the apt repositories (signed packages)"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

# The interface is created first, so the host has its public address from the first boot and the
# address stays the same when the instance is replaced.
resource "aws_network_interface" "host" {
  subnet_id       = aws_subnet.public.id
  security_groups = [aws_security_group.host.id]

  tags = { Name = "cragmatch-host" }
}

resource "aws_eip" "host" {
  domain = "vpc"

  tags = { Name = "cragmatch-host" }

  depends_on = [aws_internet_gateway.main]
}

resource "aws_eip_association" "host" {
  allocation_id        = aws_eip.host.id
  network_interface_id = aws_network_interface.host.id
}
