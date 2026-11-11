<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    exit(1);
}

$web = $argv[1] ?? '';
$command = $argv[2] ?? '';
require $web . '/api/lib.php';
$pdo = db();

if ($command === 'export') {
    $games = $pdo->query("SELECT id, user_id, side, points FROM games
                          WHERE status = 'done' AND points IS NOT NULL AND verified IS NULL")->fetchAll();
    $moves = $pdo->prepare('SELECT call_json, roll FROM game_moves WHERE game_id = ? ORDER BY n');
    foreach ($games as &$game) {
        $moves->execute([$game['id']]);
        $game['moves'] = array_map(fn ($m) => [$m['call_json'], (int) $m['roll']], $moves->fetchAll());
    }
    echo json_encode($games);
    exit(0);
}

if ($command === 'apply') {
    $verdicts = json_decode((string) file_get_contents($argv[3] ?? 'php://stdin'), true) ?: [];
    $mark = $pdo->prepare('UPDATE games SET verified = ? WHERE id = ? AND verified IS NULL');
    $rejected = [];
    foreach ($verdicts as $verdict) {
        $mark->execute([$verdict['ok'] ? 1 : 0, (int) $verdict['id']]);
        if (!$verdict['ok']) {
            $rejected[] = (int) $verdict['id'];
        }
    }
    // a rejected game cannot hold a leaderboard place: rebuild each affected best from verified-or-pending games
    foreach ($rejected as $id) {
        $row = $pdo->prepare('SELECT user_id, side FROM games WHERE id = ?');
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
    echo count($verdicts) . ' verdicts applied, ' . count($rejected) . " rejected.\n";
    exit(0);
}

fwrite(STDERR, "usage: php referee.php <web dir> export|apply [verdicts.json]\n");
exit(1);
