<?php
$config['enable_spellcheck'] = false;
$config['smtp_user'] = '';
$config['smtp_pass'] = '';
// Dovecot denies cleartext LOGIN; the image cert is local. Do not verify it.
$config['imap_conn_options'] = [
    'ssl' => [
        'verify_peer' => false,
        'verify_peer_name' => false,
        'allow_self_signed' => true,
    ],
];
