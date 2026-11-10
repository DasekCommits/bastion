<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

require_post();
start_session();
$_SESSION = [];
$params = session_get_cookie_params();
setcookie(session_name(), '', [
    'expires' => time() - 3600,
    'path' => $params['path'],
    'secure' => true,
    'httponly' => true,
    'samesite' => 'Lax',
]);
session_destroy();
send_json(['ok' => true]);
