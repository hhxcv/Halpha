import type { CompiledValidateFunction } from "@rjsf/validator-ajv8/lib/types.js";

declare const validationFunctions: Record<string, CompiledValidateFunction>;
export = validationFunctions;
