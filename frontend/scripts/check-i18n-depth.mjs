import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const root = path.resolve(import.meta.dirname, "../src/core/i18n/locales");
const locales = [
  ["en-US", "en-US.ts", "enUS"],
  ["ja", "ja.ts", "ja"],
  ["ko", "ko.ts", "ko"],
  ["zh-CN", "zh-CN.ts", "zhCN"],
  ["zh-TW", "zh-TW.ts", "zhTW"],
];

function unwrap(node) {
  while (ts.isAsExpression(node) || ts.isSatisfiesExpression(node) || ts.isParenthesizedExpression(node)) node = node.expression;
  return node;
}

function propertyName(node) {
  if (ts.isIdentifier(node) || ts.isStringLiteral(node) || ts.isNumericLiteral(node)) return node.text;
  throw new Error(`Unsupported translated property name: ${node.getText()}`);
}

function findLocaleObject(fileName, variableName) {
  const source = ts.createSourceFile(fileName, fs.readFileSync(fileName, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  for (const statement of source.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (ts.isIdentifier(declaration.name) && declaration.name.text === variableName && declaration.initializer) {
        const object = unwrap(declaration.initializer);
        if (ts.isObjectLiteralExpression(object)) return object;
      }
    }
  }
  throw new Error(`Could not find ${variableName} in ${fileName}`);
}

function flatten(object, prefix = "", result = new Map()) {
  for (const property of object.properties) {
    if (!ts.isPropertyAssignment(property) && !ts.isMethodDeclaration(property)) continue;
    const key = prefix ? `${prefix}.${propertyName(property.name)}` : propertyName(property.name);
    const value = ts.isMethodDeclaration(property) ? property : unwrap(property.initializer);
    if (ts.isObjectLiteralExpression(value)) {
      flatten(value, key, result);
      continue;
    }
    const kind = ts.isStringLiteralLike(value)
      ? "string"
      : ts.isArrowFunction(value) || ts.isFunctionExpression(value) || ts.isMethodDeclaration(value)
        ? `function:${value.parameters.length}`
        : ts.isArrayLiteralExpression(value)
          ? "array"
          : "value";
    result.set(key, kind);
  }
  return result;
}

const catalogs = new Map(
  locales.map(([locale, file, variable]) => [locale, flatten(findLocaleObject(path.join(root, file), variable))]),
);
const baseline = catalogs.get("en-US");
const failures = [];

for (const [locale, catalog] of catalogs) {
  for (const [key, kind] of baseline) {
    if (!catalog.has(key)) failures.push(`${locale}: missing ${key}`);
    else if (catalog.get(key) !== kind) failures.push(`${locale}: ${key} is ${catalog.get(key)}, expected ${kind}`);
  }
  for (const key of catalog.keys()) if (!baseline.has(key)) failures.push(`${locale}: extra ${key}`);
}

if (failures.length) {
  console.error(`i18n depth check failed (${failures.length}):\n${failures.join("\n")}`);
  process.exit(1);
}

console.log(`i18n depth check passed: ${locales.length} locales × ${baseline.size} aligned keys`);
