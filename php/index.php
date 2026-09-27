<?php
declare(strict_types=1);

const CHARLOTTE_HOST = 'webpages.charlotte.edu';
const MAX_INTRODUCTION_BYTES = 5 * 1024 * 1024;
const MAX_REQUEST_BYTES = 4096;
const MAX_TEXT_LENGTH = 20000;

final class ApiException extends RuntimeException
{
    public function __construct(public readonly int $status, string $message)
    {
        parent::__construct($message);
    }
}

function respond(int $status, mixed $payload = null): never
{
    http_response_code($status);
    if ($payload !== null) {
        try {
            echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
        } catch (JsonException) {
            http_response_code(500);
            echo '{"detail":"Could not encode the response as JSON."}';
        }
    }
    exit;
}

function configureCors(): void
{
    $allowedOrigin = getenv('INTRODUCTIONS_ALLOWED_ORIGIN') ?: 'https://webpages.charlotte.edu';
    $origin = $_SERVER['HTTP_ORIGIN'] ?? '';
    header('Vary: Origin');
    if ($origin === '' || hash_equals($allowedOrigin, $origin)) {
        header('Access-Control-Allow-Origin: ' . $allowedOrigin);
    }
    header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
    header('Access-Control-Allow-Headers: Content-Type');
    header('Access-Control-Max-Age: 600');
}

function database(): PDO
{
    $path = getenv('INTRODUCTIONS_DB_PATH');
    if (!$path) {
        throw new RuntimeException('Set INTRODUCTIONS_DB_PATH to an SQLite file outside the public web directory.');
    }

    $directory = dirname($path);
    if (!is_dir($directory) && !mkdir($directory, 0700, true) && !is_dir($directory)) {
        throw new RuntimeException('Could not create the SQLite database directory.');
    }

    $pdo = new PDO('sqlite:' . $path, null, null, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    $pdo->exec('PRAGMA busy_timeout = 5000');
    $pdo->exec(<<<'SQL'
        CREATE TABLE IF NOT EXISTS introductions (
            username TEXT PRIMARY KEY,
            json_url TEXT NOT NULL,
            base_site_url TEXT NOT NULL,
            introduction_data TEXT NOT NULL CHECK (json_valid(introduction_data)),
            updated_at TEXT NOT NULL
        )
        SQL);
    return $pdo;
}

function submittedUsername(): string
{
    $contentType = strtolower(trim(explode(';', $_SERVER['CONTENT_TYPE'] ?? '')[0]));
    if ($contentType !== 'application/json') {
        throw new ApiException(415, 'Send the submission as application/json.');
    }
    $contentLength = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
    if ($contentLength > MAX_REQUEST_BYTES) {
        throw new ApiException(413, 'The request body is too large.');
    }
    $body = file_get_contents('php://input', false, null, 0, MAX_REQUEST_BYTES + 1);
    if ($body === false || strlen($body) > MAX_REQUEST_BYTES) {
        throw new ApiException(413, 'The request body is too large.');
    }
    try {
        $submission = json_decode($body, false, 16, JSON_THROW_ON_ERROR);
    } catch (JsonException) {
        throw new ApiException(400, 'The request body must be valid JSON.');
    }
    if (!is_object($submission) || !isset($submission->username) || !is_string($submission->username)) {
        throw new ApiException(400, "Provide a JSON body with a 'username' string field.");
    }
    $username = trim($submission->username);
    if (!preg_match('/^[A-Za-z0-9][A-Za-z0-9_-]{0,38}$/D', $username)) {
        throw new ApiException(422, 'The username must contain 1–39 letters, numbers, underscores, or hyphens.');
    }
    return $username;
}

function sourceBaseUrl(): string
{
    $baseUrl = getenv('INTRODUCTIONS_SOURCE_BASE_URL') ?: 'https://' . CHARLOTTE_HOST;
    $parts = parse_url($baseUrl);
    if ($parts === false || !isset($parts['scheme'], $parts['host'])
        || isset($parts['user']) || isset($parts['pass']) || isset($parts['query']) || isset($parts['fragment'])
        || (isset($parts['path']) && $parts['path'] !== '' && $parts['path'] !== '/')) {
        throw new RuntimeException('INTRODUCTIONS_SOURCE_BASE_URL must be an origin for webpages.charlotte.edu or 127.0.0.1.');
    }

    $host = strtolower($parts['host']);
    $scheme = strtolower($parts['scheme']);
    $port = $parts['port'] ?? null;
    $isCharlotte = $host === CHARLOTTE_HOST && $scheme === 'https' && ($port === null || $port === 443);
    $isLocal = $host === '127.0.0.1' && in_array($scheme, ['http', 'https'], true);
    if (!$isCharlotte && !$isLocal) {
        throw new RuntimeException('The source host must be webpages.charlotte.edu or 127.0.0.1.');
    }

    return $scheme . '://' . $host . ($port === null ? '' : ':' . $port);
}

function introductionUrl(string $username): string
{
    $relativePath = getenv('INTRODUCTION_JSON_PATH') ?: 'itis3135/introduction_generated.json';
    $relativePath = trim($relativePath, '/');
    if ($relativePath === '' || !preg_match('/^[A-Za-z0-9._\\/-]+$/D', $relativePath)
        || in_array('..', explode('/', $relativePath), true) || in_array('.', explode('/', $relativePath), true)) {
        throw new RuntimeException('INTRODUCTION_JSON_PATH must be a relative path inside each username directory.');
    }
    return sourceBaseUrl() . '/' . rawurlencode($username) . '/' . $relativePath;
}

function fetchIntroduction(string $jsonUrl): object
{
    if (!function_exists('curl_init')) {
        throw new RuntimeException('The PHP cURL extension is required.');
    }
    $curl = curl_init($jsonUrl);
    if ($curl === false) {
        throw new ApiException(502, 'Could not initialize the Charlotte JSON fetch.');
    }

    $body = '';
    $tooLarge = false;
    curl_setopt_array($curl, [
        CURLOPT_RETURNTRANSFER => false,
        CURLOPT_FOLLOWLOCATION => false,
        CURLOPT_CONNECTTIMEOUT => 4,
        CURLOPT_TIMEOUT => 12,
        CURLOPT_PROTOCOLS => CURLPROTO_HTTP | CURLPROTO_HTTPS,
        CURLOPT_USERAGENT => 'Introduction-PHP-API/1.0',
        CURLOPT_HTTPHEADER => ['Accept: application/json'],
        CURLOPT_WRITEFUNCTION => static function ($handle, string $chunk) use (&$body, &$tooLarge): int {
            if (strlen($body) + strlen($chunk) > MAX_INTRODUCTION_BYTES) {
                $tooLarge = true;
                return 0;
            }
            $body .= $chunk;
            return strlen($chunk);
        },
    ]);
    $result = curl_exec($curl);
    $statusCode = (int)curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $curlError = curl_error($curl);
    curl_close($curl);

    if ($tooLarge) {
        throw new ApiException(413, 'The linked JSON file is larger than the 5 MiB limit.');
    }
    if ($result === false) {
        throw new ApiException(502, 'Could not fetch the introduction JSON from Charlotte: ' . ($curlError ?: 'network error') . '.');
    }
    if ($statusCode < 200 || $statusCode >= 300) {
        throw new ApiException(502, 'The Charlotte JSON URL returned HTTP ' . $statusCode . '.');
    }

    try {
        $payload = json_decode($body, false, 128, JSON_THROW_ON_ERROR);
    } catch (JsonException) {
        throw new ApiException(422, 'The linked file is not valid JSON.');
    }
    if (!is_object($payload)) {
        throw new ApiException(422, 'The linked JSON must contain an introduction object.');
    }
    validateIntroduction($payload);
    return $payload;
}

function requireString(object $object, string $field, string $label): string
{
    if (!isset($object->{$field}) || !is_string($object->{$field})) {
        throw new ApiException(422, "The {$label} value '{$field}' must be a string.");
    }
    $maximumLength = $field === 'img' ? MAX_INTRODUCTION_BYTES : MAX_TEXT_LENGTH;
    if (strlen($object->{$field}) > $maximumLength) {
        $limit = $field === 'img' ? '5 MiB' : '20,000 bytes';
        throw new ApiException(422, "The '{$field}' value exceeds the {$limit} limit.");
    }
    return $object->{$field};
}

function validateIntroduction(object $data): void
{
    $legacyFields = [
        'divider', 'personalStatement', 'personalBackground', 'professionalBackground',
        'academicBackground', 'primaryWorkComputer', 'primaryWorkLocation', 'alternateComputerLocation',
    ];
    $foundLegacy = array_values(array_filter($legacyFields, static fn(string $field): bool => property_exists($data, $field)));
    if ($foundLegacy !== []) {
        throw new ApiException(422, 'Outdated top-level keys found: ' . implode(', ', $foundLegacy)
            . ". Use 'prettyNameDivider' and group personal fields under 'personalInfo'.");
    }

    $requiredStrings = [
        'firstName', 'lastName', 'acknowledgment', 'acknowledgmentDate', 'prettyNameDivider',
        'adjectives', 'animal', 'img', 'caption', 'quote', 'quoteAuthor',
    ];
    foreach ($requiredStrings as $field) {
        requireString($data, $field, 'introduction');
    }

    foreach (['middleName', 'nickname', 'pictureAlt', 'funnyItem', 'somethingToShare'] as $field) {
        if (property_exists($data, $field) && !is_string($data->{$field})) {
            throw new ApiException(422, "The optional introduction value '{$field}' must be a string.");
        }
    }

    $imagePattern = '/^data:image\/[A-Za-z0-9.+-]+;base64,([A-Za-z0-9+\/]*={0,2})$/D';
    if (!preg_match($imagePattern, $data->img, $matches) || base64_decode($matches[1], true) === false) {
        throw new ApiException(422, "The 'img' value must be a valid Base64 data URL for an image.");
    }

    if (!isset($data->personalInfo) || !is_object($data->personalInfo)) {
        throw new ApiException(422, "The 'personalInfo' value must be an object.");
    }
    $personalInfoFields = [
        'statement', 'personalBackground', 'professionalBackground', 'academicBackground',
        'primaryWorkComputer', 'primaryWorkLocation', 'alternateComputerLocation',
    ];
    foreach ($personalInfoFields as $field) {
        requireString($data->personalInfo, $field, 'personalInfo');
    }

    if (!isset($data->courses) || !is_array($data->courses)) {
        throw new ApiException(422, "The 'courses' value must be an array.");
    }
    if (count($data->courses) > 100) {
        throw new ApiException(422, 'The introduction may contain no more than 100 courses.');
    }
    $courseFields = ['department', 'courseNumber', 'courseTitle', 'reasonForTaking'];
    foreach ($data->courses as $index => $course) {
        $number = $index + 1;
        if (!is_object($course)) {
            throw new ApiException(422, "Course {$number} must be an object.");
        }
        if (property_exists($course, 'reasonfortaking')) {
            throw new ApiException(422, "Course {$number} uses 'reasonfortaking'; rename it to 'reasonForTaking'.");
        }
        foreach ($courseFields as $field) {
            $value = requireString($course, $field, "course {$number}");
            if (trim($value) === '') {
                throw new ApiException(422, "Course {$number} has an empty '{$field}' value.");
            }
        }
    }

    if (!isset($data->footerLinks) || !is_array($data->footerLinks)) {
        throw new ApiException(422, "The 'footerLinks' value must be an array.");
    }
    if (count($data->footerLinks) > 50) {
        throw new ApiException(422, 'The introduction may contain no more than 50 footer links.');
    }
    foreach ($data->footerLinks as $index => $link) {
        $number = $index + 1;
        if (!is_object($link)) {
            throw new ApiException(422, "Footer link {$number} must be an object.");
        }
        requireString($link, 'label', "footer link {$number}");
        requireString($link, 'url', "footer link {$number}");
    }
}

function getAllIntroductions(PDO $pdo): object
{
    $rows = $pdo->query(
        'SELECT username, json_url, base_site_url, introduction_data, updated_at FROM introductions ORDER BY username'
    )->fetchAll();
    $class = [];
    foreach ($rows as $row) {
        $class[$row['username']] = [
            'lastUpdated' => $row['updated_at'],
            'jsonUrl' => $row['json_url'],
            'baseSiteUrl' => $row['base_site_url'],
            'introductionData' => json_decode($row['introduction_data'], false, 128, JSON_THROW_ON_ERROR),
        ];
    }
    return (object)$class;
}

configureCors();
header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') {
    http_response_code(204);
    exit;
}

try {
    $method = $_SERVER['REQUEST_METHOD'] ?? '';
    if ($method !== 'GET' && $method !== 'POST') {
        header('Allow: GET, POST, OPTIONS');
        throw new ApiException(405, 'Use GET to read the class data or POST to submit a username.');
    }
    $origin = $_SERVER['HTTP_ORIGIN'] ?? '';
    $allowedOrigin = getenv('INTRODUCTIONS_ALLOWED_ORIGIN') ?: 'https://webpages.charlotte.edu';
    if ($origin !== '' && !hash_equals($allowedOrigin, $origin)) {
        throw new ApiException(403, 'This browser origin is not allowed.');
    }

    if ($method === 'GET') {
        $pdo = database();
        respond(200, getAllIntroductions($pdo));
    }

    $username = submittedUsername();
    $jsonUrl = introductionUrl($username);
    $introduction = fetchIntroduction($jsonUrl);
    $updatedAt = (new DateTimeImmutable('now', new DateTimeZone('UTC')))->format('Y-m-d\TH:i:s.uP');
    $baseSiteUrl = rtrim(sourceBaseUrl(), '/') . '/' . rawurlencode($username) . '/';
    $introductionJson = json_encode($introduction, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);

    $pdo = database();
    $pdo->beginTransaction();
    $statement = $pdo->prepare(<<<'SQL'
        INSERT INTO introductions (username, json_url, base_site_url, introduction_data, updated_at)
        VALUES (:username, :json_url, :base_site_url, :introduction_data, :updated_at)
        ON CONFLICT(username) DO UPDATE SET
            json_url = excluded.json_url,
            base_site_url = excluded.base_site_url,
            introduction_data = excluded.introduction_data,
            updated_at = excluded.updated_at
        SQL);
    $statement->execute([
        ':username' => $username,
        ':json_url' => $jsonUrl,
        ':base_site_url' => $baseSiteUrl,
        ':introduction_data' => $introductionJson,
        ':updated_at' => $updatedAt,
    ]);
    $pdo->commit();

    respond(200, [
        'username' => $username,
        'lastUpdated' => $updatedAt,
        'jsonUrl' => $jsonUrl,
        'baseSiteUrl' => $baseSiteUrl,
        'introductionData' => $introduction,
    ]);
} catch (ApiException $error) {
    respond($error->status, ['detail' => $error->getMessage()]);
} catch (JsonException $error) {
    respond(500, ['detail' => 'Could not encode or decode introduction JSON.']);
} catch (PDOException $error) {
    if (isset($pdo) && $pdo instanceof PDO && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    error_log('Introduction PHP API database error: ' . $error->getMessage());
    respond(500, ['detail' => 'Could not read or update the introduction database.']);
} catch (Throwable $error) {
    if (isset($pdo) && $pdo instanceof PDO && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    error_log('Introduction PHP API error: ' . $error->getMessage());
    respond(500, ['detail' => $error->getMessage()]);
}
