<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    exit(1);
}

$web = $argv[1] ?? '';
require $web . '/api/lib.php';

db()->exec(
    'CREATE TABLE IF NOT EXISTS users (
        id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        github_id BIGINT UNSIGNED NOT NULL UNIQUE,
        login VARCHAR(64) NOT NULL,
        avatar_url VARCHAR(255) NOT NULL DEFAULT \'\',
        points INT UNSIGNED NOT NULL DEFAULT 0,
        games INT UNSIGNED NOT NULL DEFAULT 0,
        wins TEXT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login DATETIME NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
);

foreach (['secrets' => 'ALTER TABLE users ADD COLUMN secrets TEXT NULL AFTER wins',
          'realism_red' => 'ALTER TABLE users ADD COLUMN realism_red INT UNSIGNED NOT NULL DEFAULT 0',
          'realism_blue' => 'ALTER TABLE users ADD COLUMN realism_blue INT UNSIGNED NOT NULL DEFAULT 0',
          'realism_red_secs' => 'ALTER TABLE users ADD COLUMN realism_red_secs INT UNSIGNED NOT NULL DEFAULT 0',
          'realism_blue_secs' => 'ALTER TABLE users ADD COLUMN realism_blue_secs INT UNSIGNED NOT NULL DEFAULT 0'] as $col => $sql) {
    if (!db()->query("SHOW COLUMNS FROM users LIKE '$col'")->fetchAll()) {
        db()->exec($sql);
    }
}

db()->exec(
    'CREATE TABLE IF NOT EXISTS score_audit (
        id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        user_id INT UNSIGNED NOT NULL,
        side VARCHAR(8) NOT NULL,
        points INT UNSIGNED NOT NULL,
        secs INT UNSIGNED NOT NULL DEFAULT 0,
        accepted TINYINT NOT NULL DEFAULT 0,
        transcript MEDIUMTEXT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX (user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
);

echo "Tables ready.\n";
