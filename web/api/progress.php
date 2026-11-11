<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

require_post();
start_session();
$user = current_user();
if ($user === null) {
    send_json(['error' => 'Sign in first.'], 401);
}

$body = json_decode((string) file_get_contents('php://input', false, null, 0, 4096), true);
$points = $body['points'] ?? null;
$games = $body['games'] ?? null;
$wins = $body['wins'] ?? null;
$secrets = $body['secrets'] ?? [];
$learned = $body['learned'] ?? [];

if (!is_int($points) || !is_int($games) || !is_array($wins) || $points < 0 || $games < 0 || $points > 10000000 || $games > 1000000) {
    send_json(['error' => 'That progress does not look right.'], 422);
}
$clean = [];
foreach ($wins as $name => $count) {
    $name = (string) $name;
    if (in_array($name, TIERS, true)) {
        $name .= '/easy';
    }
    if (!preg_match('/^(small|medium|large)\/(easy|medium|hard|realism)$/', $name) || !is_int($count) || $count < 0 || $count > $games) {
        send_json(['error' => 'That progress does not look right.'], 422);
    }
    $clean[$name] = ($clean[$name] ?? 0) + $count;
}
$cleanSecrets = [];
if (!is_array($secrets)) {
    send_json(['error' => 'That progress does not look right.'], 422);
}
foreach ($secrets as $name => $count) {
    if (!in_array($name, ['sealed', 'script'], true) || !is_int($count) || $count < 0 || $count > $games) {
        send_json(['error' => 'That progress does not look right.'], 422);
    }
    $cleanSecrets[$name] = $count;
}
if ($games < (int) $user['games']) {
    send_json(['error' => 'Progress can only go forward.'], 409);
}
$cleanLearned = [];
if (!is_array($learned)) {
    send_json(['error' => 'That progress does not look right.'], 422);
}
foreach ($learned as $name) {
    if (is_string($name) && preg_match('/^(chain:)?[a-z0-9-]{1,32}$/', $name) && !in_array($name, $cleanLearned, true)) {
        $cleanLearned[] = $name;
    }
}

$stmt = db()->prepare('UPDATE users SET points = ?, games = ?, wins = ?, secrets = ?, learned = ? WHERE id = ?');
$stmt->execute([$points, $games, json_encode((object) $clean), json_encode((object) $cleanSecrets), json_encode(array_values($cleanLearned)), $user['id']]);
send_json(['ok' => true]);
