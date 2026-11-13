<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

require_post();

$body = json_decode((string) file_get_contents('php://input'), true);
if (!is_array($body)) {
    send_json(['error' => 'Something went wrong. Please try again.'], 400);
}

if (trim((string) ($body['website'] ?? '')) !== '') {
    send_json(['ok' => true]);
}

$kinds = ['bug', 'idea', 'balance', 'other'];
$kind = (string) ($body['kind'] ?? 'other');
$message = trim(str_replace("\r", '', (string) ($body['message'] ?? '')));
$contact = trim((string) ($body['contact'] ?? ''));
$screen = substr(preg_replace('/[^a-z0-9_-]/i', '', (string) ($body['screen'] ?? '')), 0, 40);

if (!in_array($kind, $kinds, true)) {
    $kind = 'other';
}
if (mb_strlen($message) < 5) {
    send_json(['error' => 'Please write a little more.'], 422);
}
if (mb_strlen($message) > 2000 || mb_strlen($contact) > 120) {
    send_json(['error' => 'That is a bit too long. Please keep it shorter.'], 422);
}

$ip = $_SERVER['REMOTE_ADDR'] ?? '';
$ipHash = hash_hmac('sha256', $ip, (config()['DB_PASS'] ?? '') . 'feedback');

try {
    $recent = db()->prepare('SELECT COUNT(*) FROM feedback WHERE ip_hash = ? AND created_at > (NOW() - INTERVAL 1 HOUR)');
    $recent->execute([$ipHash]);
    if ((int) $recent->fetchColumn() >= 5) {
        send_json(['error' => 'Thanks, we already got a lot from you. Try again in an hour.'], 429);
    }

    start_session();
    $user = current_user();

    $stmt = db()->prepare('INSERT INTO feedback (kind, message, contact, login, screen, agent, ip_hash) VALUES (?, ?, ?, ?, ?, ?, ?)');
    $stmt->execute([
        $kind,
        $message,
        $contact,
        $user['login'] ?? null,
        $screen,
        substr((string) ($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 255),
        $ipHash,
    ]);
} catch (Throwable $error) {
    send_json(['error' => 'Feedback is not available right now. Please try again later.'], 503);
}

send_json(['ok' => true]);
