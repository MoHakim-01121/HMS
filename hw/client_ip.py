import ipaddress


def _valid(value):
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request):
    """The visitor's address. Forwarding headers count only when the direct
    peer is on a private network, i.e. our own proxy; the rightmost
    X-Forwarded-For entry is the one that proxy appended, anything left of it
    came from the visitor."""
    peer = request.META.get('REMOTE_ADDR', '')
    peer_ip = _valid(peer)
    if peer_ip and ipaddress.ip_address(peer_ip).is_private:
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '').rsplit(',', 1)[-1]
        return _valid(forwarded) or _valid(request.META.get('HTTP_X_REAL_IP', '')) or peer_ip
    return peer_ip or peer


def client_ip_key(group, request):
    """client_ip in the form django-ratelimit calls a key function."""
    return client_ip(request)
