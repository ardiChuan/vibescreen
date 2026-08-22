import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";


const RELAY_DIR = dirname(fileURLToPath(import.meta.url));
const REAL_KV_ID = "a".repeat(32);
const ZERO_KV_ID = "0".repeat(32);

function productionConfig({
  main = "worker.js", kvId = REAL_KV_ID, name = "vibepulse-relay",
} = {}) {
  return {
    name,
    main,
    compatibility_date: "2026-08-22",
    durable_objects: {
      bindings: [{
        name: "NUMBERS_MAILBOX",
        class_name: "NumbersMailbox",
      }],
    },
    exports: {
      NumbersMailbox: { type: "durable-object", storage: "sqlite" },
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

test("valid private configs invoke pinned Wrangler only in the chosen mode",
     async (t) => {
  const { runProductionDeployment } = await import("./deploy.mjs");
  const calls = [];
  const dependencies = {
    spawnSync(command, args, spawnOptions) {
      calls.push({ command, args, spawnOptions });
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
  };
  const reorderedPath = privateConfig(t, reordered);

  runProductionDeployment(options(bootstrapPath, {
    expectedMain: "bootstrap.js",
  }), dependencies);
  runProductionDeployment(options(workerPath, { mode: "deploy" }), dependencies);
  runProductionDeployment(options(reorderedPath), dependencies);

  assert.equal(calls.length, 3);
  assert.match(calls[0].command, /node_modules[/\\]\.bin[/\\]wrangler/);
  assert.deepEqual(calls[0].args, [
    "deploy", resolve(RELAY_DIR, "bootstrap.js"),
    "--config", bootstrapPath, "--dry-run",
  ]);
  assert.deepEqual(calls[1].args, [
    "deploy", resolve(RELAY_DIR, "worker.js"), "--config", workerPath,
  ]);
  assert.deepEqual(calls[2].args, [
    "deploy", resolve(RELAY_DIR, "worker.js"),
    "--config", reorderedPath, "--dry-run",
  ]);
  assert.equal(calls[0].spawnOptions.cwd, RELAY_DIR);
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
      "--dry-run"],
    ["deploy", "--config", resolve(RELAY_DIR, "wrangler.worker.test.jsonc"),
      "--dry-run"],
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
