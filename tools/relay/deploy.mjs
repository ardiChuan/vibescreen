#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { spawnSync as nodeSpawnSync } from "node:child_process";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";


const RELAY_DIR = dirname(fileURLToPath(import.meta.url));
const REPOSITORY_ROOT = resolve(RELAY_DIR, "..", "..");
const WORKER_NAME = "vibepulse-relay";
const ZERO_KV_ID = "0".repeat(32);
const REAL_KV_ID_PATTERN = /^[0-9a-f]{32}$/;
const STAGE_MAINS = new Set(["bootstrap.js", "worker.js"]);
const TEST_CONFIGS = [
  resolve(RELAY_DIR, "wrangler.test.jsonc"),
  resolve(RELAY_DIR, "wrangler.worker.test.jsonc"),
];

function guardError(message) {
  return new Error(`deploy guard: ${message}`);
}

function isWithinRepository(path) {
  const child = relative(REPOSITORY_ROOT, path);
  return child === "" || (!child.startsWith("..") && !isAbsolute(child));
}

function pinnedWrangler() {
  const executable = process.platform === "win32" ? "wrangler.cmd" : "wrangler";
  return resolve(RELAY_DIR, "node_modules", ".bin", executable);
}

function invokeWrangler(args, { spawnSync = nodeSpawnSync } = {}) {
  const result = spawnSync(pinnedWrangler(), args, {
    cwd: RELAY_DIR,
    stdio: "inherit",
  });
  if (result.error) throw guardError("Wrangler could not start");
  if (result.status !== 0)
    throw guardError(`Wrangler exited with status ${String(result.status)}`);
}

export function validateProductionConfig(config, {
  configPath, expectedKvId, expectedMain,
}) {
  if (!isAbsolute(configPath) || isWithinRepository(resolve(configPath)) ||
      !configPath.endsWith(".json"))
    throw guardError("production config must be an absolute private .json file");
  if (!REAL_KV_ID_PATTERN.test(expectedKvId) ||
      expectedKvId === ZERO_KV_ID)
    throw guardError("expected KV ID must be a nonzero 32-character hex ID");
  if (!STAGE_MAINS.has(expectedMain))
    throw guardError("expected main must be bootstrap.js or worker.js");
  if (!config || typeof config !== "object" || Array.isArray(config))
    throw guardError("production config must be a JSON object");
  if (config.name !== WORKER_NAME)
    throw guardError("wrong Worker name");
  if (config.main !== expectedMain)
    throw guardError("wrong stage entrypoint");
  if (typeof config.compatibility_date !== "string")
    throw guardError("compatibility_date is required");
  if (Object.hasOwn(config, "migrations"))
    throw guardError("exports lifecycle cannot be mixed with migrations");

  const kvBindings = Array.isArray(config.kv_namespaces)
    ? config.kv_namespaces.filter((binding) => binding?.binding === "VIBEPULSE")
    : [];
  if (kvBindings.length !== 1 || kvBindings[0].id !== expectedKvId ||
      kvBindings[0].id === ZERO_KV_ID)
    throw guardError("VIBEPULSE must match the expected real KV namespace");

  const configuredObjectBindings = Array.isArray(
    config.durable_objects?.bindings,
  ) ? config.durable_objects.bindings : [];
  const objectBindings = configuredObjectBindings.filter(
      (binding) => binding?.name === "NUMBERS_MAILBOX",
    );
  const bindingKeys = objectBindings[0] &&
      typeof objectBindings[0] === "object"
    ? Object.keys(objectBindings[0])
    : [];
  if (configuredObjectBindings.length !== 1 ||
      objectBindings.length !== 1 ||
      objectBindings[0].class_name !== "NumbersMailbox" ||
      bindingKeys.some((key) => !["name", "class_name"].includes(key)))
    throw guardError("NUMBERS_MAILBOX must bind NumbersMailbox");
  const lifecycleExportNames = config.exports &&
      typeof config.exports === "object" && !Array.isArray(config.exports)
    ? Object.keys(config.exports)
    : [];
  if (lifecycleExportNames.length !== 1 ||
      lifecycleExportNames[0] !== "NumbersMailbox")
    throw guardError("NumbersMailbox must be the only lifecycle export");
  const mailboxExport = config.exports?.NumbersMailbox;
  const exportKeys = mailboxExport && typeof mailboxExport === "object"
    ? Object.keys(mailboxExport)
    : [];
  if (mailboxExport?.type !== "durable-object" ||
      mailboxExport?.storage !== "sqlite" ||
      (mailboxExport.state !== undefined && mailboxExport.state !== "created") ||
      exportKeys.some((key) => !["type", "storage", "state"].includes(key)))
    throw guardError("NumbersMailbox must be a SQLite Durable Object export");
  if (!Array.isArray(config.secrets?.required) ||
      !config.secrets.required.includes("RELAY_SECRET"))
    throw guardError("RELAY_SECRET must be declared as required");
  if (config.vars && Object.hasOwn(config.vars, "RELAY_SECRET"))
    throw guardError("RELAY_SECRET must not be stored in plaintext vars");
}

export function runProductionDeployment(options, dependencies = {}) {
  const {
    mode, configPath, expectedKvId, expectedMain,
  } = options;
  if (mode !== "dry-run" && mode !== "deploy")
    throw guardError("mode must be dry-run or deploy");
  if (typeof configPath !== "string")
    throw guardError("--config is required");

  let config;
  try {
    config = JSON.parse(readFileSync(configPath, "utf8"));
  } catch {
    throw guardError("production config must be readable strict JSON");
  }
  validateProductionConfig(config, {
    configPath,
    expectedKvId,
    expectedMain,
  });

  // The private config deliberately lives outside the repository. Supplying the
  // validated absolute entrypoint keeps Wrangler from resolving `main` relative
  // to that private file's directory.
  const args = [
    "deploy", resolve(RELAY_DIR, expectedMain), "--config", configPath,
  ];
  if (mode === "dry-run") args.push("--dry-run");
  invokeWrangler(args, dependencies);
}

export function runCiDryBuild(dependencies = {}) {
  for (const configPath of TEST_CONFIGS)
    invokeWrangler(
      ["deploy", "--config", configPath, "--dry-run"],
      dependencies,
    );
}

function parseProductionArgs(mode, args) {
  const values = {};
  for (let index = 0; index < args.length; index += 2) {
    const flag = args[index];
    const value = args[index + 1];
    if (!["--config", "--expected-kv-id", "--expected-main"].includes(flag) ||
        value === undefined || Object.hasOwn(values, flag))
      throw guardError("required flags are --config, --expected-kv-id, --expected-main");
    values[flag] = value;
  }
  return {
    mode,
    configPath: values["--config"],
    expectedKvId: values["--expected-kv-id"],
    expectedMain: values["--expected-main"],
  };
}

export function runCli(args, dependencies = {}) {
  const [mode, ...rest] = args;
  if (mode === "ci-dry") {
    if (rest.length !== 0) throw guardError("ci-dry accepts no arguments");
    runCiDryBuild(dependencies);
    return;
  }
  runProductionDeployment(parseProductionArgs(mode, rest), dependencies);
}

const invokedPath = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href
                                    : "";
if (import.meta.url === invokedPath) {
  try {
    runCli(process.argv.slice(2));
  } catch (error) {
    console.error(error instanceof Error ? error.message : "deploy guard: failed");
    process.exitCode = 1;
  }
}
