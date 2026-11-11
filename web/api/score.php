<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

require_post();
start_session();
$user = current_user();
if ($user === null) {
    send_json(['error' => 'Sign in first.'], 401);
}

$body = json_decode((string) file_get_contents('php://input', false, null, 0, 262144), true);
$side = $body['side'] ?? '';
$points = $body['points'] ?? null;
$secs = $body['seconds'] ?? null;
$transcript = $body['transcript'] ?? null;

if (!in_array($side, ['red', 'blue'], true) || !is_int($points) || $points < 0) {
    send_json(['error' => 'That score does not look right.'], 422);
}

// Coarse server-side sanity gate. The game runs in the browser, so this cannot
// prove a score, but it rejects the impossible: the real ceiling is 180 Red /
// 130 Blue, doubled to 360 / 260 only on a won random-side game. Anything above
// could not have come from a real game, so we refuse it. The transcript below is
// the real check — it is replayed offline against the engine to confirm a score.
$ceiling = $side === 'red' ? 360 : 260;
if ($points > $ceiling) {
    record_audit($user['id'], $side, $points, 0, false, $transcript);
    send_json(['error' => 'That score is higher than any real game can reach.'], 422);
}

if (!is_int($secs) || $secs < 1 || $secs > 86400) {
    $secs = 0;  // unknown / untrusted duration; ranks last among ties
}

record_audit($user['id'], $side, $points, $secs, true, $transcript);

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


function record_audit(int $userId, string $side, int $points, int $secs, bool $accepted, $transcript): void
{
    try {
        $json = $transcript === null ? null : json_encode($transcript);
        if ($json !== null && strlen($json) > 200000) {
            $json = null;  // too large to keep; drop rather than fail the submission
        }
        $stmt = db()->prepare('INSERT INTO score_audit (user_id, side, points, secs, accepted, transcript) VALUES (?, ?, ?, ?, ?, ?)');
        $stmt->execute([$userId, $side, $points, $secs, $accepted ? 1 : 0, $json]);
    } catch (Throwable $error) {
        error_log('Bastion score_audit: ' . $error->getMessage());
    }
}
