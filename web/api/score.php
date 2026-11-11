<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

require_post();
start_session();
$user = current_user();
if ($user === null) {
    send_json(['error' => 'Sign in first.'], 401);
}

$body = json_decode((string) file_get_contents('php://input', false, null, 0, 2048), true);
$side = $body['side'] ?? '';
$points = $body['points'] ?? null;

if (!in_array($side, ['red', 'blue'], true) || !is_int($points) || $points < 0 || $points > 1000) {
    send_json(['error' => 'That score does not look right.'], 422);
}

$column = $side === 'red' ? 'realism_red' : 'realism_blue';
$best = max((int) $user[$column], $points);
$stmt = db()->prepare("UPDATE users SET $column = ? WHERE id = ?");
$stmt->execute([$best, $user['id']]);
send_json(['ok' => true, 'best' => $best]);
