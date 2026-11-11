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
$secs = $body['seconds'] ?? null;

if (!in_array($side, ['red', 'blue'], true) || !is_int($points) || $points < 0 || $points > 1000) {
    send_json(['error' => 'That score does not look right.'], 422);
}
if (!is_int($secs) || $secs < 1 || $secs > 86400) {
    $secs = 0;  // unknown / untrusted duration; ranks last among ties
}

$column = $side === 'red' ? 'realism_red' : 'realism_blue';
$timeColumn = $column . '_secs';
$bestPoints = (int) $user[$column];
$bestSecs = (int) $user[$timeColumn];

// keep the highest score; on a tie, keep the faster real-time run
$beats = $points > $bestPoints
    || ($points === $bestPoints && $secs > 0 && ($bestSecs === 0 || $secs < $bestSecs));
if ($beats) {
    $stmt = db()->prepare("UPDATE users SET $column = ?, $timeColumn = ? WHERE id = ?");
    $stmt->execute([$points, $secs, $user['id']]);
    send_json(['ok' => true, 'best' => $points, 'seconds' => $secs]);
}
send_json(['ok' => true, 'best' => $bestPoints, 'seconds' => $bestSecs]);
