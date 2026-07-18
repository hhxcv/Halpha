import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import compileSchemaValidators from "@rjsf/validator-ajv8/compileSchemaValidators";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const frontendDirectory = resolve(scriptDirectory, "..");
const registryPath = resolve(frontendDirectory, "..", "src", "halpha", "planning", "strategy_registry.json");
const generatedDirectory = resolve(frontendDirectory, "src", "generated");
const strategyId = "ONE_SHOT_DONCHIAN_ATR_BREAKOUT";

const registry = JSON.parse(readFileSync(registryPath, "utf8"));
const definition = registry.strategies.find((candidate) => candidate.strategy_id === strategyId);
if (!definition) {
  throw new Error(`The canonical strategy registry does not contain ${strategyId}.`);
}

const schemaPath = resolve(generatedDirectory, "oneShotStrategySchema.json");
const validatorPath = resolve(generatedDirectory, "oneShotStrategyValidator.cjs");
writeFileSync(schemaPath, `${JSON.stringify(definition.parameter_schema, null, 2)}\n`, "utf8");
compileSchemaValidators(definition.parameter_schema, validatorPath, { AjvClass: Ajv2020 });
process.stdout.write(`${JSON.stringify({ status: "STRATEGY_VALIDATOR_GENERATED", strategy_id: strategyId })}\n`);
