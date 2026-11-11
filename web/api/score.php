<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

require_post();
start_session();
$user = current_user();
if ($user === null) {
    send_json(['error' => 'Sign in first.'], 401);
}

$body = json_decode((string) file_get_contents('php://input', false, null, 0, 16384), true);
$side = $body['side'] ?? '';
$points = $body['points'] ?? null;
$secs = $body['seconds'] ?? null;
$gameId = $body['game'] ?? null;

if (!in_array($side, ['red', 'blue'], true) || !is_int($points) || $points < 0 || !is_int($gameId)) {
    send_json(['error' => 'That score does not look right.'], 422);
}

// The real ceiling is 180 Red / 130 Blue, doubled only on a won random-side game.
$ceiling = $side === 'red' ? 360 : 260;
if ($points > $ceiling) {
    send_json(['error' => 'That score is higher than any real game can reach.'], 422);
}
if (!is_int($secs) || $secs < 1 || $secs > 86400) {
    $secs = 0;
}

// The score must belong to a finished game whose dice the server rolled. The claim is
// stored on that game; the referee replays its moves with the same dice to confirm it.
$pdo = db();
$stmt = $pdo->prepare("UPDATE games SET side = ?, points = ?, secs = ?
                       WHERE id = ? AND user_id = ? AND status = 'done' AND points IS NULL");
$stmt->execute([$side, $points, $secs, $gameId, $user['id']]);
if ($stmt->rowCount() !== 1) {
    send_json(['error' => 'No finished game to attach this score to.'], 409);
}

$column = $side === 'red' ? 'realism_red' : 'realism_blue';
$timeColumn = $column . '_secs';
$bestPoints = (int) $user[$column];
$bestSecs = (int) $user[$timeColumn];

$beats = $points > $bestPoints
    || ($points === $bestPoints && $secs > 0 && ($bestSecs === 0 || $secs < $bestSecs));
if ($beats) {
    $pdo->prepare("UPDATE users SET $column = ?, $timeColumn = ? WHERE id = ?")->execute([$points, $secs, $user['id']]);
    send_json(['ok' => true, 'best' => $points, 'seconds' => $secs]);
}
send_json(['ok' => true, 'best' => $bestPoints, 'seconds' => $bestSecs]);
