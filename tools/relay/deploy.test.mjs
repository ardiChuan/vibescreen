import assert from "node:assert/strict";
import {
  existsSync, mkdtempSync, readFileSync, rmSync, statSync, symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";


const RELAY_DIR = dirname(fileURLToPath(import.meta.url));
const REPOSITORY_ROOT = resolve(RELAY_DIR, "..", "..");
const REAL_KV_ID = "a".repeat(32);
const ZERO_KV_ID = "0".repeat(32);

function productionConfig({
  main = "worker.js", kvId = REAL_KV_ID, name = "vibepulse-relay",
} = {}) {
  return {
    name,
    main,
    compatibility_date: "2026-08-22",
    compatibility_flags: ["nodejs_compat"],
    observability: { enabled: true },
    durable_objects: {
      bindings: [{
        name: "NUMBERS_MAILBOX",
        class_name: "NumbersMailbox",
      }],
    },
    exports: {
      NumbersMailbox: {
        type: "durable-object", storage: "sqlite", state: "created",
      },
    },
    kv_namespaces: [{ binding: "VIBEPULSE", id: kvId }],
    secrets: { required: ["RELAY_SECRET"] },
  };
}

function privateConfig(t, config = productionConfig()) {
  const directory = mkdtempSync(join(tmpdir(), "vibepulse-relay-config-"));
  t.after(() => rmSync(directory, { recursive: true }));
  const configPath = join(directory, "production.json");
  writeFileSync(configPath, JSON.stringify(config), "utf8");
  return configPath;
}

function options(configPath, overrides = {}) {
  return {
    mode: "dry-run",
    configPath,
    expectedKvId: REAL_KV_ID,
    expectedMain: "worker.js",
    ...overrides,
  };
}

test("invalid production configs never reach a child process", async (t) => {
  const { runProductionDeployment, validateProductionConfig } =
    await import("./deploy.mjs");
  let childCalls = 0;
  const dependencies = {
    spawnSync() {
      childCalls += 1;
      return { status: 0 };
    },
  };

  const missingKv = productionConfig();
  delete missingKv.kv_namespaces;
  const missingBinding = productionConfig();
  delete missingBinding.durable_objects;
  const missingExport = productionConfig();
  delete missingExport.exports;
  const wrongBinding = productionConfig();
  wrongBinding.durable_objects.bindings[0].class_name = "WrongMailbox";
  const remoteBinding = productionConfig();
  remoteBinding.durable_objects.bindings[0].script_name = "other-worker";
  const wrongExport = productionConfig();
  wrongExport.exports.NumbersMailbox.storage = "legacy-kv";
  const extraLifecycleExport = productionConfig();
  extraLifecycleExport.exports.RetiredMailbox = { state: "deleted" };
  const missingSecret = productionConfig();
  delete missingSecret.secrets;
  const plaintextSecret = productionConfig();
  plaintextSecret.vars = { RELAY_SECRET: "must-not-be-committed" };
  const ordinaryVar = productionConfig();
  ordinaryVar.vars = { ENVIRONMENT: "production" };
  const routes = productionConfig();
  routes.routes = ["example.com/*"];
  const environment = productionConfig();
  environment.env = { production: {} };
  const otherBindingFamily = productionConfig();
  otherBindingFamily.r2_buckets = [{
    binding: "ARCHIVE", bucket_name: "not-allowed",
  }];
  const arbitraryTopLevel = productionConfig();
  arbitraryTopLevel.send_metrics = false;
  const wrongDate = productionConfig();
  wrongDate.compatibility_date = "2026-08-21";
  const missingFlags = productionConfig();
  delete missingFlags.compatibility_flags;
  const extraFlag = productionConfig();
  extraFlag.compatibility_flags.push("experimental");
  const wrongObservability = productionConfig();
  wrongObservability.observability.enabled = false;
  const extraObservabilityKey = productionConfig();
  extraObservabilityKey.observability.head_sampling_rate = 1;
  const extraKv = productionConfig();
  extraKv.kv_namespaces.push({
    binding: "OTHER_KV", id: "c".repeat(32),
  });
  const extraKvKey = productionConfig();
  extraKvKey.kv_namespaces[0].preview_id = REAL_KV_ID;
  const extraDurableObjectKey = productionConfig();
  extraDurableObjectKey.durable_objects.extra = true;
  const missingExportState = productionConfig();
  delete missingExportState.exports.NumbersMailbox.state;
  const extraSecret = productionConfig();
  extraSecret.secrets.required.push("OTHER_SECRET");
  const extraSecretsKey = productionConfig();
  extraSecretsKey.secrets.extra = true;

  const repositoryDirectory = mkdtempSync(
    join(RELAY_DIR, ".production-config-test-"),
  );
  t.after(() => rmSync(repositoryDirectory, { recursive: true, force: true }));
  const repositoryConfig = join(repositoryDirectory, "production.json");
  writeFileSync(repositoryConfig, JSON.stringify(productionConfig()), "utf8");
  const symlinkDirectory = mkdtempSync(
    join(tmpdir(), "vibepulse-relay-symlink-"),
  );
  t.after(() => rmSync(symlinkDirectory, { recursive: true, force: true }));
  const repositoryConfigSymlink = join(symlinkDirectory, "production.json");
  symlinkSync(repositoryConfig, repositoryConfigSymlink);

  const invalid = [
    options(privateConfig(t, productionConfig({ name: "wrong-worker" }))),
    options(privateConfig(t, productionConfig({ main: "wrong.js" }))),
    options(privateConfig(t, missingKv)),
    options(privateConfig(t, productionConfig({ kvId: "b".repeat(32) }))),
    options(privateConfig(t, missingBinding)),
    options(privateConfig(t, wrongBinding)),
    options(privateConfig(t, remoteBinding)),
    options(privateConfig(t, missingExport)),
    options(privateConfig(t, wrongExport)),
    options(privateConfig(t, extraLifecycleExport)),
    options(privateConfig(t, missingSecret)),
    options(privateConfig(t, plaintextSecret)),
    options(privateConfig(t, ordinaryVar)),
    options(privateConfig(t, routes)),
    options(privateConfig(t, environment)),
    options(privateConfig(t, otherBindingFamily)),
    options(privateConfig(t, arbitraryTopLevel)),
    options(privateConfig(t, wrongDate)),
    options(privateConfig(t, missingFlags)),
    options(privateConfig(t, extraFlag)),
    options(privateConfig(t, wrongObservability)),
    options(privateConfig(t, extraObservabilityKey)),
    options(privateConfig(t, extraKv)),
    options(privateConfig(t, extraKvKey)),
    options(privateConfig(t, extraDurableObjectKey)),
    options(privateConfig(t, missingExportState)),
    options(privateConfig(t, extraSecret)),
    options(privateConfig(t, extraSecretsKey)),
    options(repositoryConfigSymlink),
    options(privateConfig(t), { expectedKvId: ZERO_KV_ID }),
    options(privateConfig(t), { expectedMain: "wrong.js" }),
    options(resolve(RELAY_DIR, "wrangler.test.jsonc")),
  ];

  for (const invalidOptions of invalid)
    assert.throws(
      () => runProductionDeployment(invalidOptions, dependencies),
      /deploy guard:/,
    );
  assert.throws(() => validateProductionConfig(productionConfig(), {
    configPath: resolve(RELAY_DIR, "..", "private.json"),
    expectedKvId: REAL_KV_ID,
    expectedMain: "worker.js",
  }), /absolute private/);
  assert.equal(childCalls, 0);
});

test("valid private configs invoke pinned Wrangler with private canonical snapshots",
     async (t) => {
  const { runProductionDeployment } = await import("./deploy.mjs");
  const calls = [];
  let originalPath;
  const dependencies = {
    spawnSync(command, args, spawnOptions) {
      const snapshotPath = args[args.indexOf("--config") + 1];
      writeFileSync(originalPath, JSON.stringify({ hijacked: true }), "utf8");
      const snapshotBytes = readFileSync(snapshotPath, "utf8");
      const snapshotMode = statSync(snapshotPath).mode & 0o777;
      calls.push({
        command, args, spawnOptions, snapshotPath, snapshotBytes, snapshotMode,
      });
      return { status: 0 };
    },
  };
  const bootstrapPath = privateConfig(
    t, productionConfig({ main: "bootstrap.js" }),
  );
  const workerPath = privateConfig(t);
  const reordered = productionConfig();
  reordered.exports.NumbersMailbox = {
    storage: "sqlite",
    type: "durable-object",
    state: "created",
  };
  const reorderedPath = privateConfig(t, reordered);

  originalPath = bootstrapPath;
  runProductionDeployment(options(bootstrapPath, {
    expectedMain: "bootstrap.js",
  }), dependencies);
  originalPath = workerPath;
  runProductionDeployment(options(workerPath, { mode: "deploy" }), dependencies);
  originalPath = reorderedPath;
  runProductionDeployment(options(reorderedPath), dependencies);

  assert.equal(calls.length, 3);
  assert.match(calls[0].command, /node_modules[/\\]\.bin[/\\]wrangler/);
  assert.deepEqual(calls[0].args.filter((arg) => arg !== calls[0].snapshotPath), [
    "deploy", resolve(RELAY_DIR, "bootstrap.js"),
    "--config", "--strict", "--keep-vars", "--dry-run",
  ]);
  assert.deepEqual(calls[1].args.filter((arg) => arg !== calls[1].snapshotPath), [
    "deploy", resolve(RELAY_DIR, "worker.js"),
    "--config", "--strict", "--keep-vars",
  ]);
  assert.deepEqual(calls[2].args.filter((arg) => arg !== calls[2].snapshotPath), [
    "deploy", resolve(RELAY_DIR, "worker.js"),
    "--config", "--strict", "--keep-vars", "--dry-run",
  ]);
  assert.equal(calls[0].spawnOptions.cwd, RELAY_DIR);
  assert.equal(calls[0].snapshotBytes,
               `${JSON.stringify(productionConfig({ main: "bootstrap.js" }), null, 2)}\n`);
  assert.equal(calls[1].snapshotBytes,
               `${JSON.stringify(productionConfig(), null, 2)}\n`);
  assert.equal(calls[2].snapshotBytes,
               `${JSON.stringify(productionConfig(), null, 2)}\n`);
  for (const call of calls) {
    assert.equal(call.snapshotMode, 0o600);
    assert.ok(isAbsolute(call.snapshotPath));
    const repositoryRelative = relative(REPOSITORY_ROOT, call.snapshotPath);
    assert.ok(repositoryRelative.startsWith("..") ||
              isAbsolute(repositoryRelative));
    assert.equal(existsSync(call.snapshotPath), false);
    assert.equal(existsSync(dirname(call.snapshotPath)), false);
  }
});

test("private snapshots are removed after Wrangler failure or interrupt",
     async (t) => {
  const { runProductionDeployment } = await import("./deploy.mjs");
  for (const result of [
    { status: 17 },
    { status: null, signal: "SIGINT" },
  ]) {
    let snapshotPath;
    assert.throws(() => runProductionDeployment(options(privateConfig(t)), {
      spawnSync(_command, args) {
        snapshotPath = args[args.indexOf("--config") + 1];
        assert.equal(existsSync(snapshotPath), true);
        return result;
      },
    }), /deploy guard:/);
    assert.equal(existsSync(snapshotPath), false);
    assert.equal(existsSync(dirname(snapshotPath)), false);
  }
});

test("CI dry build compiles both staged entrypoints without a deploy mode",
     async () => {
  const { runCiDryBuild } = await import("./deploy.mjs");
  const calls = [];
  runCiDryBuild({
    spawnSync(command, args) {
      calls.push({ command, args });
      return { status: 0 };
    },
  });

  assert.equal(calls.length, 2);
  assert.deepEqual(calls.map((call) => call.args), [
    ["deploy", "--config", resolve(RELAY_DIR, "wrangler.test.jsonc"),
      "--strict", "--keep-vars", "--dry-run"],
    ["deploy", "--config", resolve(RELAY_DIR, "wrangler.worker.test.jsonc"),
      "--strict", "--keep-vars", "--dry-run"],
  ]);
  for (const call of calls) {
    assert.match(call.command, /node_modules[/\\]\.bin[/\\]wrangler/);
    assert.ok(call.args.includes("--dry-run"));
  }
});

test("committed configs are test-only while plain Wrangler is disabled",
     () => {
  const defaultConfig = JSON.parse(
    readFileSync(join(RELAY_DIR, "wrangler.jsonc"), "utf8"),
  );
  assert.equal(defaultConfig.main, "DEPLOY_DISABLED_USE_GUARD.js");
  assert.equal(defaultConfig.kv_namespaces, undefined);

  for (const [file, main] of [
    ["wrangler.test.jsonc", "bootstrap.js"],
    ["wrangler.worker.test.jsonc", "worker.js"],
  ]) {
    const config = JSON.parse(readFileSync(join(RELAY_DIR, file), "utf8"));
    assert.match(config.name, /-test$/);
    assert.equal(config.main, main);
    assert.deepEqual(config.secrets, { required: ["RELAY_SECRET"] });
    assert.deepEqual(config.durable_objects.bindings, [{
      name: "NUMBERS_MAILBOX", class_name: "NumbersMailbox",
    }]);
    assert.deepEqual(config.exports.NumbersMailbox, {
      type: "durable-object", storage: "sqlite",
    });
    assert.deepEqual(config.kv_namespaces, [{
      binding: "VIBEPULSE", id: ZERO_KV_ID,
    }]);
  }
});
