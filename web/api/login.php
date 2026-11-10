<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

start_session();
$state = bin2hex(random_bytes(16));
$_SESSION['oauth_state'] = $state;

$query = http_build_query([
    'client_id' => config()['GITHUB_CLIENT_ID'] ?? '',
    'redirect_uri' => ORIGIN . '/api/callback.php',
    'state' => $state,
    'allow_signup' => 'true',
]);

header('Cache-Control: no-store');
header('Location: https://github.com/login/oauth/authorize?' . $query, true, 302);
