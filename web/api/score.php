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
if ($points > ($side === 'red' ? 360 : 260)) {
    send_json(['error' => 'That score is higher than any real game can reach.'], 422);
}
if (!is_int($secs) || $secs < 1 || $secs > 86400) {
    $secs = 0;
}

// The map and difficulty come from the server's own log of the game, never from the page.
$pdo = db();
$start = $pdo->prepare("SELECT m.call_json FROM game_moves m JOIN games g ON g.id = m.game_id
                        WHERE m.game_id = ? AND m.n = 0 AND g.user_id = ?");
$start->execute([$gameId, $user['id']]);
$call = json_decode((string) $start->fetchColumn(), true);
$company = $call[1][0] ?? null;
$level = $call[1][1] ?? null;
if (!is_string($company) || !in_array($level, ['easy', 'medium', 'hard', 'realism'], true)) {
    send_json(['error' => 'No finished game to attach this score to.'], 409);
}

// The referee replays the game with the same dice and rejects the claim if it does not match.
$stmt = $pdo->prepare("UPDATE games SET side = ?, points = ?, secs = ?, level = ?, company = ?
                       WHERE id = ? AND user_id = ? AND status = 'done' AND points IS NULL");
$stmt->execute([$side, $points, $secs, $level, substr($company, 0, 32), $gameId, $user['id']]);
if ($stmt->rowCount() !== 1) {
    send_json(['error' => 'No finished game to attach this score to.'], 409);
}
send_json(['ok' => true, 'level' => $level]);
