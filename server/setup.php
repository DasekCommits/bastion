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
          'realism_blue_secs' => 'ALTER TABLE users ADD COLUMN realism_blue_secs INT UNSIGNED NOT NULL DEFAULT 0',
          'learned' => 'ALTER TABLE users ADD COLUMN learned TEXT NULL'] as $col => $sql) {
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

db()->exec(
    'CREATE TABLE IF NOT EXISTS games (
        id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        user_id INT UNSIGNED NOT NULL,
        secret CHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL DEFAULT \'live\',
        moves INT UNSIGNED NOT NULL DEFAULT 0,
        side VARCHAR(8) NULL,
        points INT UNSIGNED NULL,
        secs INT UNSIGNED NOT NULL DEFAULT 0,
        verified TINYINT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at DATETIME NULL,
        INDEX (user_id, status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
);

db()->exec(
    'CREATE TABLE IF NOT EXISTS game_moves (
        game_id INT UNSIGNED NOT NULL,
        n INT UNSIGNED NOT NULL,
        call_json TEXT NOT NULL,
        roll BIGINT UNSIGNED NOT NULL,
        PRIMARY KEY (game_id, n)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
);

foreach (['users' => ['achievements' => 'ALTER TABLE users ADD COLUMN achievements TEXT NULL',
                      'owned' => 'ALTER TABLE users ADD COLUMN owned TEXT NULL',
                      'gifted' => 'ALTER TABLE users ADD COLUMN gifted TEXT NULL',
                      'migrated' => 'ALTER TABLE users ADD COLUMN migrated TINYINT NOT NULL DEFAULT 0'],
          'games' => ['summary' => 'ALTER TABLE games ADD COLUMN summary TEXT NULL',
                      'level' => 'ALTER TABLE games ADD COLUMN level VARCHAR(10) NULL',
                      'company' => 'ALTER TABLE games ADD COLUMN company VARCHAR(32) NULL',
                      'shop' => 'ALTER TABLE games ADD COLUMN shop TINYINT NOT NULL DEFAULT 0']] as $table => $columns) {
    foreach ($columns as $col => $sql) {
        if (!db()->query("SHOW COLUMNS FROM $table LIKE '$col'")->fetchAll()) {
            db()->exec($sql);
        }
    }
}

db()->exec(
    'CREATE TABLE IF NOT EXISTS feedback (
        id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        kind VARCHAR(16) NOT NULL,
        message TEXT NOT NULL,
        contact VARCHAR(120) NOT NULL DEFAULT \'\',
        login VARCHAR(64) NULL,
        screen VARCHAR(40) NOT NULL DEFAULT \'\',
        agent VARCHAR(255) NOT NULL DEFAULT \'\',
        ip_hash CHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL DEFAULT \'new\',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX (ip_hash, created_at),
        INDEX (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
);

db()->exec('UPDATE users SET migrated = 1 WHERE games > 0');

echo "Tables ready.\n";
