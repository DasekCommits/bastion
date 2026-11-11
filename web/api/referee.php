<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

// Only the referee (a scheduled GitHub Actions job) may call this, with a shared token.
$token = config()['REFEREE_TOKEN'] ?? '';
$given = preg_replace('/^Bearer\s+/', '', $_SERVER['HTTP_AUTHORIZATION'] ?? '');
if (strlen($token) < 32 || !hash_equals($token, (string) $given)) {
    send_json(['error' => 'Not the referee.'], 403);
}

$pdo = db();
$method = $_SERVER['REQUEST_METHOD'] ?? '';

if ($method === 'GET') {
    $games = $pdo->query("SELECT id, user_id, status, side, points FROM games
                          WHERE status IN ('done', 'abandoned') AND verified IS NULL ORDER BY id LIMIT 200")->fetchAll();
    $moves = $pdo->prepare('SELECT call_json, roll FROM game_moves WHERE game_id = ? ORDER BY n');
    $history = [];
    $past = $pdo->prepare('SELECT summary FROM games WHERE user_id = ? AND verified = 1 AND summary IS NOT NULL ORDER BY id');
    foreach ($games as &$game) {
        $moves->execute([$game['id']]);
        $game['moves'] = array_map(fn ($m) => [$m['call_json'], (int) $m['roll']], $moves->fetchAll());
        $game['points'] = $game['points'] === null ? null : (int) $game['points'];
        $uid = (string) $game['user_id'];
        if (!isset($history[$uid])) {
            $past->execute([$game['user_id']]);
            $history[$uid] = array_map(fn ($r) => json_decode($r['summary'], true), $past->fetchAll());
        }
    }
    send_json(['games' => $games, 'history' => (object) $history]);
}

if ($method !== 'POST') {
    send_json(['error' => 'Use GET or POST.'], 405);
}

$body = json_decode((string) file_get_contents('php://input', false, null, 0, 4194304), true);
$verdicts = $body['verdicts'] ?? [];
$earned = $body['achievements'] ?? [];
if (!is_array($verdicts) || !is_array($earned)) {
    send_json(['error' => 'Bad verdicts.'], 422);
}

$mark = $pdo->prepare('UPDATE games SET verified = ?, summary = ? WHERE id = ? AND verified IS NULL');
$rejected = [];
foreach ($verdicts as $verdict) {
    $ok = !empty($verdict['ok']);
    $summary = isset($verdict['summary']) ? json_encode($verdict['summary']) : null;
    $mark->execute([$ok ? 1 : 0, $summary, (int) $verdict['id']]);
    if (!$ok) {
        $rejected[] = (int) $verdict['id'];
    }
}

// a rejected game cannot hold a leaderboard place: rebuild that best from the games still standing
foreach ($rejected as $id) {
    $row = $pdo->prepare('SELECT user_id, side FROM games WHERE id = ? AND side IS NOT NULL');
    $row->execute([$id]);
    $game = $row->fetch();
    if (!$game) {
        continue;
    }
    $column = $game['side'] === 'red' ? 'realism_red' : 'realism_blue';
    $best = $pdo->prepare("SELECT points, secs FROM games WHERE user_id = ? AND side = ? AND points IS NOT NULL
                           AND (verified IS NULL OR verified = 1) ORDER BY points DESC, secs = 0, secs LIMIT 1");
    $best->execute([$game['user_id'], $game['side']]);
    $top = $best->fetch() ?: ['points' => 0, 'secs' => 0];
    $pdo->prepare("UPDATE users SET $column = ?, {$column}_secs = ? WHERE id = ?")
        ->execute([(int) $top['points'], (int) $top['secs'], $game['user_id']]);
}

// achievements only ever grow
$read = $pdo->prepare('SELECT achievements FROM users WHERE id = ?');
$write = $pdo->prepare('UPDATE users SET achievements = ? WHERE id = ?');
foreach ($earned as $userId => $ids) {
    if (!is_array($ids)) {
        continue;
    }
    $read->execute([(int) $userId]);
    $have = json_decode((string) ($read->fetchColumn() ?: '[]'), true) ?: [];
    $clean = array_filter($ids, fn ($id) => is_string($id) && preg_match('/^[a-z-]{1,32}$/', $id));
    $all = array_values(array_unique(array_merge($have, $clean)));
    sort($all);
    $write->execute([json_encode($all), (int) $userId]);
}

send_json(['ok' => true, 'checked' => count($verdicts), 'rejected' => count($rejected)]);
