// Used by tests/test_saved_lectures.py.
// A small stand-in for Supabase: auth admin users, PostgREST inserts/updates/selects on the harness tables and
// the phone_lectures view, and Storage uploads and public downloads. Enough for lib/store.ts and SavedLectures.
const http = require("http");
const crypto = require("crypto");
const fs = require("fs");

const users = [];
const tables = { projects: [], scenes: [], scene_versions: [], builds: [], assets: [], build_assets: [] };
const objects = new Map();   // "bucket/path" -> Buffer
const log = [];

function json(res, code, body) {
  res.writeHead(code, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

function phoneLectures() {
  return tables.builds.filter((b) => b.published).map((b) => {
    const v = tables.scene_versions.find((x) => x.id === b.scene_version_id);
    const s = tables.scenes.find((x) => x.id === v.scene_id);
    const p = tables.projects.find((x) => x.id === s.project_id);
    return {
      build_id: b.id, project_id: p.id, series: p.title, subject: p.subject ?? null, language: p.language ?? null,
      lecture: s.ordinal, lectures: s.part_of ?? 1, title: s.title || p.title, minutes: s.minutes ?? null,
      library_path: b.library_path, library_bytes: b.library_bytes, program_bytes: b.program_bytes,
      frame_count: b.frame_count, fps: b.fps, narrated: b.audio_path != null, saved_at: b.finished_at,
    };
  });
}

const server = http.createServer((req, res) => {
  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    const body = Buffer.concat(chunks);
    const url = new URL(req.url, "http://x");
    log.push(`${req.method} ${url.pathname}${url.search}`);
    // Auth admin
    if (url.pathname === "/auth/v1/admin/users") {
      if (req.method === "GET") return json(res, 200, { users, aud: "authenticated" });
      const input = JSON.parse(body.toString() || "{}");
      const user = { id: crypto.randomUUID(), email: input.email, aud: "authenticated" };
      users.push(user);
      return json(res, 200, user);
    }
    // Storage
    let m = /^\/storage\/v1\/object\/public\/([^/]+)\/(.+)$/.exec(url.pathname);
    if (m && req.method === "GET") {
      const key = `${m[1]}/${decodeURIComponent(m[2])}`;
      if (!objects.has(key)) return json(res, 400, { statusCode: "404", error: "not_found", message: "Object not found" });
      res.writeHead(200, { "Content-Type": "application/octet-stream" });
      return res.end(objects.get(key));
    }
    m = /^\/storage\/v1\/object\/([^/]+)\/(.+)$/.exec(url.pathname);
    if (m && (req.method === "POST" || req.method === "PUT")) {
      const key = `${m[1]}/${decodeURIComponent(m[2])}`;
      const upsert = req.headers["x-upsert"] === "true";
      if (objects.has(key) && !upsert) {
        return json(res, 400, { statusCode: "409", error: "Duplicate", message: "The resource already exists" });
      }
      // supabase-js sends a Buffer body as is, or multipart form data.
      let data = body;
      const type = req.headers["content-type"] || "";
      if (type.startsWith("multipart/form-data")) {
        const boundary = "--" + /boundary=(.+)$/.exec(type)[1];
        const text = body.toString("latin1");
        const part = text.split(boundary).find((p) => /name="file"|filename=/.test(p) || /name=""/.test(p)) ?? text.split(boundary)[1];
        const start = part.indexOf("\r\n\r\n") + 4;
        data = Buffer.from(part.slice(start, part.length - 2), "latin1");
      }
      objects.set(key, data);
      return json(res, 200, { Key: key, Id: crypto.randomUUID() });
    }
    // PostgREST
    m = /^\/rest\/v1\/([a-z_]+)$/.exec(url.pathname);
    if (m) {
      const table = m[1];
      const single = (req.headers["accept"] || "").includes("vnd.pgrst.object");
      if (req.method === "GET" && table === "phone_lectures") return json(res, 200, phoneLectures());
      if (req.method === "POST") {
        const rows = [].concat(JSON.parse(body.toString()));
        const prefer = req.headers["prefer"] || "";
        const out = [];
        for (const row of rows) {
          if (table === "assets" && tables.assets.some((a) => a.digest === row.digest)) {
            if (prefer.includes("ignore-duplicates")) continue;
            return json(res, 409, { message: "duplicate key value violates unique constraint \"assets_pkey\"" });
          }
          const stored = { id: row.id ?? crypto.randomUUID(), created_at: new Date().toISOString(), ...row };
          if (table === "assets" || table === "build_assets") delete stored.id;
          tables[table].push(stored);
          out.push(stored);
        }
        if (single) return json(res, 201, out[0]);
        return json(res, 201, prefer.includes("return=representation") ? out : null);
      }
      if (req.method === "PATCH") {
        const patch = JSON.parse(body.toString());
        const id = (url.searchParams.get("id") || "").replace(/^eq\./, "");
        const row = tables[table].find((r) => r.id === id);
        if (!row) return json(res, 404, { message: "no row" });
        Object.assign(row, patch);
        res.writeHead(204);
        return res.end();
      }
    }
    if (url.pathname === "/__dump") return json(res, 200, { users, tables, objects: [...objects.keys()], log });
    json(res, 404, { message: `mock: no route for ${req.method} ${url.pathname}` });
  });
});
server.listen(Number(process.env.PORT || 54399), () => console.error("mock supabase up"));
