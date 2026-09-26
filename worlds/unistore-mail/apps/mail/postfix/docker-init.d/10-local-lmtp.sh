# Local delivery: every recipient goes to Dovecot LMTP as the original
# local-part. Sourced by boky /scripts/run.sh — do not `set -u`.
postconf -e mydestination=
postconf -e relayhost=
postconf -e relay_domains=
postconf -e local_recipient_maps=
postconf -X virtual_alias_maps
postconf -X virtual_alias_domains
postconf -X virtual_mailbox_domains
postconf -X virtual_mailbox_maps
postconf -X virtual_transport
postconf -e default_transport=lmtp:inet:dovecot:31025
postconf -e relay_transport=lmtp:inet:dovecot:31025
postconf -e mailbox_transport=lmtp:inet:dovecot:31025
postconf -e local_transport=lmtp:inet:dovecot:31025
postconf -e smtpd_reject_unlisted_recipient=no
postconf -e smtpd_recipient_restrictions=permit_mynetworks,reject
postconf -e smtpd_relay_restrictions=permit_mynetworks,reject
postconf -e lmtp_tls_security_level=none
postconf -e smtp_tls_security_level=none
