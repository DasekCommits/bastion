<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

const LEVELS = ['easy', 'medium', 'hard', 'realism'];

start_session();
$level = (string) ($_GET['level'] ?? 'easy');
if (!in_array($level, LEVELS, true)) {
    send_json(['error' => 'Unknown difficulty.'], 422);
}

try {
    $pdo = db();
    $me = current_user();
    $board = [];
    $mine = ['login' => $me['login'] ?? null];
    // best verified (or not yet checked) score per player and side; a tie goes to the faster real-time run
    $stmt = $pdo->prepare("SELECT u.id, u.login, u.avatar_url, g.points, g.secs, g.company
        FROM games g JOIN users u ON u.id = g.user_id
        WHERE g.level = ? AND g.side = ? AND g.points IS NOT NULL AND (g.verified IS NULL OR g.verified = 1)
        ORDER BY g.points DESC, (g.secs = 0) ASC, g.secs ASC, g.id ASC");
    foreach (['red', 'blue'] as $side) {
        $stmt->execute([$level, $side]);
        $seen = [];
        $rows = [];
        foreach ($stmt->fetchAll() as $r) {
            if (isset($seen[$r['id']])) {
                continue;
            }
            $seen[$r['id']] = true;
            $entry = ['login' => $r['login'], 'avatar' => $r['avatar_url'], 'score' => (int) $r['points'],
                      'secs' => (int) $r['secs'], 'map' => $r['company']];
            if ($me !== null && (int) $r['id'] === (int) $me['id']) {
                $mine[$side] = $entry;
            }
            if (count($rows) < 20) {
                $rows[] = $entry;
            }
        }
        $board[$side] = $rows;
    }
} catch (Throwable $error) {
    error_log('Bastion leaderboard: ' . $error->getMessage());
    send_json(['error' => 'The leaderboard is not available right now.'], 503);
}

send_json(['level' => $level, 'board' => $board, 'me' => $me === null ? null : $mine]);
