<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

start_session();
try {
    $pdo = db();
    $board = [];
    foreach (['red' => 'realism_red', 'blue' => 'realism_blue'] as $side => $column) {
        // highest score first; on a tie, the faster real-time run (0 = unknown, ranks last)
        $stmt = $pdo->query("SELECT login, avatar_url, $column AS score, {$column}_secs AS secs
            FROM users WHERE $column > 0
            ORDER BY score DESC, (secs = 0) ASC, secs ASC, last_login ASC LIMIT 20");
        $board[$side] = array_map(static fn($r) => [
            'login' => $r['login'],
            'avatar' => $r['avatar_url'],
            'score' => (int) $r['score'],
            'secs' => (int) $r['secs'],
        ], $stmt->fetchAll());
    }
    $me = current_user();
    $mine = null;
    if ($me !== null) {
        $mine = [
            'red' => (int) $me['realism_red'], 'red_secs' => (int) $me['realism_red_secs'],
            'blue' => (int) $me['realism_blue'], 'blue_secs' => (int) $me['realism_blue_secs'],
            'login' => $me['login'],
        ];
    }
} catch (Throwable $error) {
    error_log('Bastion leaderboard: ' . $error->getMessage());
    send_json(['error' => 'The leaderboard is not available right now.'], 503);
}

send_json(['board' => $board, 'me' => $mine]);
