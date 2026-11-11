<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

const MOVES = ['start', 'set_defenses', 'set_arsenal', 'begin', 'move', 'end_day', 'give_up', 'finish',
               'blue_act', 'blue_wait', 'terminal', 'realism_search', 'realism_act', 'realism_wait'];
const LAST_MOVES = ['finish', 'give_up'];
const MAX_MOVES = 5000;

require_post();
start_session();
$user = current_user();
if ($user === null) {
    send_json(['error' => 'Sign in first.'], 401);
}

$body = json_decode((string) file_get_contents('php://input', false, null, 0, 65536), true);
$n = $body['n'] ?? null;
$call = $body['call'] ?? null;
$gameId = $body['game'] ?? null;

$valid = is_int($n) && $n >= 0 && $n < MAX_MOVES
    && is_array($call) && count($call) === 2
    && is_string($call[0] ?? null) && in_array($call[0], MOVES, true)
    && is_array($call[1] ?? null);
$callJson = $valid ? json_encode($call, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) : false;
if (!$valid || $callJson === false || strlen($callJson) > 4000) {
    send_json(['error' => 'That move does not look right.'], 422);
}

$pdo = db();
$pdo->beginTransaction();

if ($n === 0) {
    if ($call[0] !== 'start' || $gameId !== null) {
        $pdo->rollBack();
        send_json(['error' => 'A game starts with start.'], 422);
    }
    $pdo->prepare("UPDATE games SET status = 'abandoned' WHERE user_id = ? AND status = 'live'")->execute([$user['id']]);
    $pdo->prepare("INSERT INTO games (user_id, secret, status, moves, shop) VALUES (?, ?, 'live', 0, 1)")
        ->execute([$user['id'], bin2hex(random_bytes(32))]);
    $gameId = (int) $pdo->lastInsertId();
}

if (!is_int($gameId)) {
    $pdo->rollBack();
    send_json(['error' => 'Which game?'], 422);
}

$stmt = $pdo->prepare('SELECT id, secret, status, moves FROM games WHERE id = ? AND user_id = ? FOR UPDATE');
$stmt->execute([$gameId, $user['id']]);
$game = $stmt->fetch();
if (!$game) {
    $pdo->rollBack();
    send_json(['error' => 'No such game.'], 404);
}

$played = (int) $game['moves'];
if ($n < $played) {
    $stmt = $pdo->prepare('SELECT call_json, roll FROM game_moves WHERE game_id = ? AND n = ?');
    $stmt->execute([$gameId, $n]);
    $old = $stmt->fetch();
    $pdo->commit();
    if ($old && $old['call_json'] === $callJson) {
        send_json(['game' => $gameId, 'n' => $n, 'roll' => (int) $old['roll']]);
    }
    send_json(['error' => 'That move was already played differently.'], 409);
}
if ($n > $played || $game['status'] !== 'live') {
    $pdo->rollBack();
    send_json(['error' => $game['status'] === 'live' ? 'Moves arrived out of order.' : 'This game is over.'], 409);
}

$roll = hexdec(substr(hash_hmac('sha256', $gameId . ':' . $n, hex2bin($game['secret'])), 0, 13));
$pdo->prepare('INSERT INTO game_moves (game_id, n, call_json, roll) VALUES (?, ?, ?, ?)')
    ->execute([$gameId, $n, $callJson, $roll]);
$final = in_array($call[0], LAST_MOVES, true);
$pdo->prepare($final
    ? "UPDATE games SET moves = ?, status = 'done', finished_at = NOW() WHERE id = ?"
    : 'UPDATE games SET moves = ? WHERE id = ?')
    ->execute([$n + 1, $gameId]);
$pdo->commit();

send_json(['game' => $gameId, 'n' => $n, 'roll' => $roll]);
