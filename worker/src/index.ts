interface Env {
  DB: D1Database;
}

interface IntroductionRecord {
  username: string;
  json_url: string;
  base_site_url: string;
  introduction_data: string;
  updated_at: string;
}

const ALLOWED_HOST = "webpages.charlotte.edu";
const MAX_JSON_SIZE = 5 * 1024 * 1024;
const REQUIRED_FIELDS = [
  "firstName", "lastName", "acknowledgment", "acknowledgmentDate", "prettyNameDivider",
  "adjectives", "animal", "img", "caption", "personalInfo",
  "courses", "quote", "quoteAuthor", "footerLinks",
] as const;
const PERSONAL_INFO_FIELDS = [
  "statement", "personalBackground", "professionalBackground", "academicBackground",
  "primaryWorkComputer", "primaryWorkLocation", "alternateComputerLocation",
] as const;
const COURSE_FIELDS = ["department", "courseNumber", "courseTitle", "reasonForTaking"] as const;
const LEGACY_TOP_LEVEL_FIELDS = [
  "divider", "personalStatement", "personalBackground", "professionalBackground",
  "academicBackground", "primaryWorkComputer", "primaryWorkLocation", "alternateComputerLocation",
] as const;

class RequestError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=0, s-maxage=30, stale-while-revalidate=60",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function usernameFromUrl(value: string): { username: string; url: URL } {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new RequestError(422, "The JSON URL is malformed.");
  }
  if (url.protocol !== "https:" || url.hostname.toLowerCase() !== ALLOWED_HOST) {
    throw new RequestError(422, `The JSON URL must use HTTPS on ${ALLOWED_HOST}.`);
  }
  if (url.username || url.password || (url.port && url.port !== "443")) {
    throw new RequestError(422, "The JSON URL must not contain credentials or a nonstandard port.");
  }

  const pathParts = url.pathname.split("/").filter(Boolean);
  if (pathParts.length < 2 || !pathParts.at(-1)?.toLowerCase().endsWith(".json")) {
    throw new RequestError(422, "Provide a direct .json file inside a username directory.");
  }
  const username = pathParts[0];
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(username)) {
    throw new RequestError(422, "The username in the JSON URL is invalid.");
  }
  return { username, url };
}

function validateIntroduction(payload: unknown): Record<string, unknown> {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new RequestError(422, "The linked JSON must contain an introduction object.");
  }
  const data = payload as Record<string, unknown>;
  const legacyFields = LEGACY_TOP_LEVEL_FIELDS.filter((field) => field in data);
  if (legacyFields.length) {
    throw new RequestError(422, `Outdated top-level keys found: ${legacyFields.join(", ")}. Use 'prettyNameDivider' and group personal fields under 'personalInfo'.`);
  }
  const missing = REQUIRED_FIELDS.filter((field) => !(field in data));
  if (missing.length) {
    throw new RequestError(422, `The introduction JSON is missing required keys: ${missing.join(", ")}.`);
  }

  for (const field of REQUIRED_FIELDS.filter((key) => key !== "courses" && key !== "footerLinks" && key !== "personalInfo")) {
    if (typeof data[field] !== "string") {
      throw new RequestError(422, `The introduction value '${field}' must be a string.`);
    }
  }
  if (!data.personalInfo || typeof data.personalInfo !== "object" || Array.isArray(data.personalInfo)) {
    throw new RequestError(422, "The 'personalInfo' value must be an object.");
  }
  const personalInfo = data.personalInfo as Record<string, unknown>;
  const missingPersonalFields = PERSONAL_INFO_FIELDS.filter((field) => !(field in personalInfo));
  if (missingPersonalFields.length) {
    throw new RequestError(422, `The 'personalInfo' object is missing keys: ${missingPersonalFields.join(", ")}.`);
  }
  for (const field of PERSONAL_INFO_FIELDS) {
    if (typeof personalInfo[field] !== "string") {
      throw new RequestError(422, `The personalInfo value '${field}' must be a string.`);
    }
  }

  const imageMatch = /^data:image\/[A-Za-z0-9.+-]+;base64,([A-Za-z0-9+/]*={0,2})$/.exec(data.img as string);
  if (!imageMatch) throw new RequestError(422, "The 'img' value must be a Base64 data URL for an image.");
  try {
    atob(imageMatch[1]);
  } catch {
    throw new RequestError(422, "The 'img' value contains invalid Base64 data.");
  }

  if (!Array.isArray(data.courses)) {
    throw new RequestError(422, "The 'courses' value must be a list.");
  }
  for (const [index, course] of data.courses.entries()) {
    if (!course || typeof course !== "object" || Array.isArray(course)) {
      throw new RequestError(422, `Course ${index + 1} must be an object.`);
    }
    const values = course as Record<string, unknown>;
    if ("reasonfortaking" in values) {
      throw new RequestError(422, `Course ${index + 1} uses 'reasonfortaking'; rename it to 'reasonForTaking'.`);
    }
    const missingCourseFields = COURSE_FIELDS.filter((field) => !(field in values));
    if (missingCourseFields.length) {
      throw new RequestError(422, `Course ${index + 1} is missing keys: ${missingCourseFields.join(", ")}.`);
    }
    for (const field of COURSE_FIELDS) {
      if (typeof values[field] !== "string" || !values[field].trim()) {
        throw new RequestError(422, `Course ${index + 1} has an empty or invalid '${field}' value.`);
      }
    }
  }

  if (!Array.isArray(data.footerLinks)) {
    throw new RequestError(422, "The 'footerLinks' value must be a list.");
  }
  for (const [index, link] of data.footerLinks.entries()) {
    if (!link || typeof link !== "object" || Array.isArray(link)
      || typeof (link as Record<string, unknown>).label !== "string"
      || typeof (link as Record<string, unknown>).url !== "string") {
      throw new RequestError(422, `Footer link ${index + 1} must have string 'label' and 'url' values.`);
    }
  }
  return data;
}

async function fetchIntroduction(initialUrl: URL): Promise<Record<string, unknown>> {
  let url = initialUrl;
  let response: Response | undefined;
  for (let redirects = 0; redirects <= 5; redirects++) {
    if (url.protocol !== "https:" || url.hostname.toLowerCase() !== ALLOWED_HOST) {
      throw new RequestError(422, `The JSON URL redirected away from ${ALLOWED_HOST}.`);
    }
    try {
      response = await fetch(url, {
        redirect: "manual",
        signal: AbortSignal.timeout(20_000),
        headers: { "User-Agent": "Introduction-Data-Worker/1.0" },
      });
    } catch (error) {
      const detail = error instanceof Error && error.name === "TimeoutError"
        ? "Timed out while fetching the JSON file."
        : "Could not fetch the JSON file.";
      throw new RequestError(502, detail);
    }
    if (![301, 302, 303, 307, 308].includes(response.status)) break;
    const location = response.headers.get("Location");
    if (!location || redirects === 5) {
      throw new RequestError(502, "The JSON URL redirected too many times or had an invalid redirect.");
    }
    url = new URL(location, url);
  }

  if (!response || response.status < 200 || response.status >= 300) {
    throw new RequestError(502, `The JSON URL returned HTTP ${response?.status ?? "an unknown status"}.`);
  }
  const contentLength = Number(response.headers.get("Content-Length") ?? 0);
  if (contentLength > MAX_JSON_SIZE) {
    throw new RequestError(413, "The JSON file is larger than the 5 MiB limit.");
  }
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > MAX_JSON_SIZE) {
    throw new RequestError(413, "The JSON file is larger than the 5 MiB limit.");
  }
  let payload: unknown;
  try {
    payload = JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: false }).decode(bytes));
  } catch {
    throw new RequestError(422, "The linked file is not valid UTF-8 JSON.");
  }
  return validateIntroduction(payload);
}

async function listIntroductions(db: D1Database): Promise<Response> {
  const { results } = await db.prepare(
    "SELECT username, json_url, base_site_url, introduction_data, updated_at FROM introductions ORDER BY username",
  ).all<IntroductionRecord>();
  const records: Record<string, unknown> = {};
  for (const record of results) {
    records[record.username] = {
      lastUpdated: record.updated_at,
      jsonUrl: record.json_url,
      baseSiteUrl: record.base_site_url,
      introductionData: JSON.parse(record.introduction_data),
    };
  }
  return jsonResponse(records);
}

async function getIntroduction(db: D1Database, username: string): Promise<Response> {
  const record = await db.prepare(
    "SELECT username, json_url, base_site_url, introduction_data, updated_at FROM introductions WHERE username = ?",
  ).bind(username).first<IntroductionRecord>();
  if (!record) throw new RequestError(404, `No introduction found for '${username}'.`);
  return jsonResponse({
    lastUpdated: record.updated_at,
    jsonUrl: record.json_url,
    baseSiteUrl: record.base_site_url,
    introductionData: JSON.parse(record.introduction_data),
  });
}

async function submitIntroduction(request: Request, db: D1Database): Promise<Response> {
  if (!request.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    throw new RequestError(415, "Send the submission as application/json.");
  }
  const requestLength = Number(request.headers.get("content-length") ?? 0);
  if (requestLength > 4096) throw new RequestError(413, "The submission body is too large.");
  let body: unknown;
  const reader = request.body?.getReader();
  if (!reader) throw new RequestError(400, "The request body is empty.");
  const chunks: Uint8Array[] = [];
  let bodySize = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bodySize += value.byteLength;
      if (bodySize > 4096) {
        await reader.cancel();
        throw new RequestError(413, "The submission body is too large.");
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(bodySize);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    body = JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: false }).decode(bytes));
  } catch (error) {
    if (error instanceof RequestError) throw error;
    throw new RequestError(400, "The request body must be valid JSON.");
  }
  if (!body || typeof body !== "object" || typeof (body as Record<string, unknown>).json_url !== "string") {
    throw new RequestError(400, "Provide a JSON body with a 'json_url' string field.");
  }
  const jsonUrl = (body as { json_url: string }).json_url.trim();
  const { username } = usernameFromUrl(jsonUrl);
  const data = await fetchIntroduction(new URL(jsonUrl));
  const updatedAt = new Date().toISOString();
  const baseSiteUrl = `https://${ALLOWED_HOST}/${username}/`;
  await db.prepare(`
    INSERT INTO introductions (username, json_url, base_site_url, introduction_data, updated_at)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(username) DO UPDATE SET
      json_url = excluded.json_url,
      base_site_url = excluded.base_site_url,
      introduction_data = excluded.introduction_data,
      updated_at = excluded.updated_at
  `).bind(username, jsonUrl, baseSiteUrl, JSON.stringify(data), updatedAt).run();

  return jsonResponse({
    username,
    lastUpdated: updatedAt,
    jsonUrl,
    baseSiteUrl,
    introductionData: data,
  }, 201);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "OPTIONS") return jsonResponse(null, 204);
    const { pathname } = new URL(request.url);
    try {
      if (request.method === "GET" && (pathname === "/" || pathname === "/sites")) {
        return await listIntroductions(env.DB);
      }
      const usernameMatch = /^\/sites\/([A-Za-z0-9][A-Za-z0-9_-]*)\/?$/.exec(pathname);
      if (request.method === "GET" && usernameMatch) {
        return await getIntroduction(env.DB, usernameMatch[1]);
      }
      if (request.method === "POST" && pathname === "/sites") {
        return await submitIntroduction(request, env.DB);
      }
      return jsonResponse({ detail: "Not found." }, 404);
    } catch (error) {
      if (error instanceof RequestError) return jsonResponse({ detail: error.message }, error.status);
      console.error("Introduction Worker request failed", error);
      return jsonResponse({ detail: "An internal error occurred." }, 500);
    }
  },
} satisfies ExportedHandler<Env>;
