<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

function back(string $result): never
{
    header('Cache-Control: no-store');
    header('Location: ' . ORIGIN . '/?signin=' . $result, true, 302);
    exit;
}

start_session();
$expected = $_SESSION['oauth_state'] ?? '';
unset($_SESSION['oauth_state']);
$state = $_GET['state'] ?? '';
$code = $_GET['code'] ?? '';

if (!is_string($expected) || $expected === '' || !is_string($state) || !hash_equals($expected, $state)) {
    back('failed');
}
if (!is_string($code) || $code === '' || strlen($code) > 200) {
    back('cancelled');
}

try {
    $config = config();
    $token = github_request('https://github.com/login/oauth/access_token', [
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => ['Accept: application/json'],
        CURLOPT_POSTFIELDS => http_build_query([
            'client_id' => $config['GITHUB_CLIENT_ID'] ?? '',
            'client_secret' => $config['GITHUB_CLIENT_SECRET'] ?? '',
            'code' => $code,
            'redirect_uri' => ORIGIN . '/api/callback.php',
        ]),
    ]);
    if (!isset($token['access_token']) || !is_string($token['access_token'])) {
        back('failed');
    }
    $github = github_request('https://api.github.com/user', [
        CURLOPT_HTTPHEADER => [
            'Accept: application/vnd.github+json',
            'Authorization: Bearer ' . $token['access_token'],
        ],
    ]);
    if (!isset($github['id'], $github['login']) || !is_int($github['id'])) {
        back('failed');
    }

    $pdo = db();
    $stmt = $pdo->prepare(
        'INSERT INTO users (github_id, login, avatar_url, last_login) VALUES (?, ?, ?, NOW())
         ON DUPLICATE KEY UPDATE login = VALUES(login), avatar_url = VALUES(avatar_url), last_login = NOW()'
    );
    $stmt->execute([$github['id'], substr((string) $github['login'], 0, 64), substr((string) ($github['avatar_url'] ?? ''), 0, 255)]);
    $find = $pdo->prepare('SELECT id FROM users WHERE github_id = ?');
    $find->execute([$github['id']]);
    $id = (int) $find->fetchColumn();
} catch (Throwable $error) {
    error_log('Bastion sign-in: ' . $error->getMessage());
    back('failed');
}

session_regenerate_id(true);
$_SESSION['user_id'] = $id;
back('ok');
