<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

start_session();
try {
    $user = current_user();
} catch (Throwable $error) {
    error_log('Bastion me: ' . $error->getMessage());
    send_json(['error' => 'Accounts are not available right now.'], 503);
}

if ($user === null) {
    send_json(['signed_in' => false]);
}

send_json([
    'signed_in' => true,
    'user' => ['login' => $user['login'], 'avatar' => $user['avatar_url']],
    'profile' => [
        'points' => (int) $user['points'],
        'games' => (int) $user['games'],
        'wins' => json_decode((string) $user['wins'], true) ?: new stdClass(),
        'secrets' => json_decode((string) $user['secrets'], true) ?: new stdClass(),
        'learned' => json_decode((string) ($user['learned'] ?? ''), true) ?: [],
        'achievements' => json_decode((string) ($user['achievements'] ?? ''), true) ?: [],
    ],
]);
