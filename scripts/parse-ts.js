#!/usr/bin/env node
/**
 * TypeScript/JavaScript parser for lerigou.
 * Uses @babel/parser to extract code structure and outputs JSON.
 *
 * Usage: node parse-ts.js <file_path>
 *
 * Output: JSON structure compatible with lerigou's CodeElement model
 */

import { readFileSync } from "fs";
import { basename, extname } from "path";
import { parse } from "@babel/parser";
import _traverse from "@babel/traverse";
import * as t from "@babel/types";

// Handle ESM default export
const traverse = _traverse.default || _traverse;

/**
 * Parse a TypeScript/JavaScript file and extract code structure.
 */
function parseFile(filePath) {
  const code = readFileSync(filePath, "utf-8");
  const ext = extname(filePath).toLowerCase();
  const isTypeScript = ext === ".ts" || ext === ".tsx";
  const isJSX = ext === ".tsx" || ext === ".jsx";

  const ast = parse(code, {
    sourceType: "module",
    plugins: [
      isTypeScript ? "typescript" : null,
      isJSX || isTypeScript ? "jsx" : null,
      "decorators-legacy",
      "classProperties",
      "classPrivateProperties",
      "classPrivateMethods",
      "exportDefaultFrom",
      "dynamicImport",
      "optionalChaining",
      "nullishCoalescingOperator",
    ].filter(Boolean),
    errorRecovery: true,
  });

  const result = {
    name: basename(filePath, ext),
    element_type: "module",
    source_file: filePath,
    line_number: 1,
    end_line_number: code.split("\n").length,
    docstring: null,
    children: [],
    imports: [],
    calls: [],
    api_calls: [],
    exports: [],
  };

  // Track current context for nested elements
  const context = {
    currentClass: null,
    currentFunction: null,
  };

  traverse(ast, {
    // Import declarations
    ImportDeclaration(path) {
      const node = path.node;
    const importInfo = {
      module: node.source.value,
      names: [],
      alias: null,
      is_from: true,
      line_number: node.loc?.start.line || 0,
      specifiers: [],
    };

      for (const specifier of node.specifiers) {
        if (t.isImportDefaultSpecifier(specifier)) {
          importInfo.names.push("default");
          importInfo.alias = specifier.local.name;
          importInfo.specifiers.push({ imported: "default", local: specifier.local.name });
        } else if (t.isImportNamespaceSpecifier(specifier)) {
          importInfo.names.push("*");
          importInfo.alias = specifier.local.name;
          importInfo.specifiers.push({ imported: "*", local: specifier.local.name });
        } else if (t.isImportSpecifier(specifier)) {
          const imported = t.isIdentifier(specifier.imported)
            ? specifier.imported.name
            : specifier.imported.value;
          importInfo.names.push(imported);
          if (specifier.local.name !== imported) {
            importInfo.alias = specifier.local.name;
          }
          importInfo.specifiers.push({ imported, local: specifier.local.name });
        }
      }

      result.imports.push(importInfo);
    },

    // Function declarations (including async)
    FunctionDeclaration(path) {
      if (path.parent.type === "ExportDefaultDeclaration" || path.parent.type === "ExportNamedDeclaration") {
        return; // Will be handled by export visitor
      }
      const funcElement = extractFunction(path.node, code);
      result.children.push(funcElement);
    },

    // Arrow functions assigned to variables
    VariableDeclaration(path) {
      for (const declarator of path.node.declarations) {
        if (
          t.isIdentifier(declarator.id) &&
          (t.isArrowFunctionExpression(declarator.init) ||
            t.isFunctionExpression(declarator.init))
        ) {
          const funcElement = extractFunction(declarator.init, code, declarator.id.name);
          funcElement.line_number = path.node.loc?.start.line || 0;
          result.children.push(funcElement);
        }
      }
    },

    // Class declarations
    ClassDeclaration(path) {
      if (path.parent.type === "ExportDefaultDeclaration" || path.parent.type === "ExportNamedDeclaration") {
        return; // Will be handled by export visitor
      }
      const classElement = extractClass(path.node, code);
      result.children.push(classElement);
    },

    // Export declarations
    ExportNamedDeclaration(path) {
      const decl = path.node.declaration;
      if (t.isFunctionDeclaration(decl)) {
        const funcElement = extractFunction(decl, code);
        funcElement.decorators.push("export");
        result.children.push(funcElement);
        result.exports.push(funcElement.name);
      } else if (t.isClassDeclaration(decl)) {
        const classElement = extractClass(decl, code);
        classElement.decorators.push("export");
        result.children.push(classElement);
        result.exports.push(classElement.name);
      } else if (t.isVariableDeclaration(decl)) {
        for (const declarator of decl.declarations) {
          if (
            t.isIdentifier(declarator.id) &&
            (t.isArrowFunctionExpression(declarator.init) ||
              t.isFunctionExpression(declarator.init))
          ) {
            const funcElement = extractFunction(declarator.init, code, declarator.id.name);
            funcElement.line_number = path.node.loc?.start.line || 0;
            funcElement.decorators.push("export");
            result.children.push(funcElement);
            result.exports.push(declarator.id.name);
          }
        }
      }
    },

    ExportDefaultDeclaration(path) {
      const decl = path.node.declaration;
      if (t.isFunctionDeclaration(decl)) {
        const funcElement = extractFunction(decl, code);
        funcElement.decorators.push("export default");
        result.children.push(funcElement);
        result.exports.push("default");
      } else if (t.isClassDeclaration(decl)) {
        const classElement = extractClass(decl, code);
        classElement.decorators.push("export default");
        result.children.push(classElement);
        result.exports.push("default");
      } else if (t.isIdentifier(decl)) {
        result.exports.push(decl.name);
      }
    },

    // Call expressions - for function calls and API calls
    CallExpression(path) {
      const call = extractCall(path.node);
      if (call) {
        // Check if it's an API call
        const apiCall = detectAPICall(path.node, code);
        if (apiCall) {
          result.api_calls.push(apiCall);
        } else {
          result.calls.push(call);
        }
      }
    },
  });

  return result;
}

/**
 * Extract function information from a function node.
 */
function extractFunction(node, code, name = null) {
  const funcName = name || node.id?.name || "anonymous";
  const isAsync = node.async || false;
  const isGenerator = node.generator || false;

  // Extract parameters
  const parameters = node.params.map((param) => {
    if (t.isIdentifier(param)) {
      return {
        name: param.name,
        type_hint: param.typeAnnotation
          ? extractTypeAnnotation(param.typeAnnotation)
          : null,
        default_value: null,
        is_args: false,
        is_kwargs: false,
      };
    } else if (t.isAssignmentPattern(param)) {
      return {
        name: t.isIdentifier(param.left) ? param.left.name : "param",
        type_hint: param.left.typeAnnotation
          ? extractTypeAnnotation(param.left.typeAnnotation)
          : null,
        default_value: extractDefaultValue(param.right, code),
        is_args: false,
        is_kwargs: false,
      };
    } else if (t.isRestElement(param)) {
      return {
        name: t.isIdentifier(param.argument) ? param.argument.name : "rest",
        type_hint: param.typeAnnotation
          ? extractTypeAnnotation(param.typeAnnotation)
          : null,
        default_value: null,
        is_args: true,
        is_kwargs: false,
      };
    } else if (t.isObjectPattern(param)) {
      return {
        name: "props",
        type_hint: param.typeAnnotation
          ? extractTypeAnnotation(param.typeAnnotation)
          : null,
        default_value: null,
        is_args: false,
        is_kwargs: true,
      };
    }
    return { name: "param", type_hint: null, default_value: null, is_args: false, is_kwargs: false };
  });

  // Extract return type
  let returnType = null;
  if (node.returnType) {
    returnType = extractTypeAnnotation(node.returnType);
  }

  // Extract docstring (JSDoc comment)
  let docstring = null;
  if (node.leadingComments) {
    const jsdoc = node.leadingComments.find((c) => c.type === "CommentBlock" && c.value.startsWith("*"));
    if (jsdoc) {
      docstring = jsdoc.value.replace(/^\*\s?/gm, "").trim();
    }
  }

  // Check if it's a React component (returns JSX)
  const isReactComponent = detectReactComponent(node);

  // Extract function calls within this function
  const calls = [];
  const apiCalls = [];

  if (node.body) {
    traverseFunctionBody(node.body, calls, apiCalls, code);
  }

  return {
    name: funcName,
    element_type: isReactComponent ? "component" : "function",
    source_file: "",
    line_number: node.loc?.start.line || 0,
    end_line_number: node.loc?.end.line || 0,
    docstring,
    parameters,
    return_type: returnType,
    is_async: isAsync,
    is_generator: isGenerator,
    decorators: [],
    base_classes: [],
    calls,
    api_calls: apiCalls,
    imports: [],
    inputs: [],
    outputs: [],
    children: [],
  };
}

/**
 * Extract class information.
 */
function extractClass(node, code) {
  const className = node.id?.name || "AnonymousClass";
  const baseClasses = [];

  if (node.superClass) {
    if (t.isIdentifier(node.superClass)) {
      baseClasses.push(node.superClass.name);
    } else if (t.isMemberExpression(node.superClass)) {
      baseClasses.push(extractMemberExpression(node.superClass));
    }
  }

  // Extract docstring
  let docstring = null;
  if (node.leadingComments) {
    const jsdoc = node.leadingComments.find((c) => c.type === "CommentBlock" && c.value.startsWith("*"));
    if (jsdoc) {
      docstring = jsdoc.value.replace(/^\*\s?/gm, "").trim();
    }
  }

  // Extract methods
  const children = [];
  for (const member of node.body.body) {
    if (t.isClassMethod(member) || t.isClassPrivateMethod(member)) {
      const methodName = t.isIdentifier(member.key)
        ? member.key.name
        : t.isPrivateName(member.key)
        ? `#${member.key.id.name}`
        : "method";

      const methodElement = extractFunction(member, code, methodName);
      methodElement.element_type = "method";
      children.push(methodElement);
    } else if (t.isClassProperty(member) || t.isClassPrivateProperty(member)) {
      const propName = t.isIdentifier(member.key)
        ? member.key.name
        : t.isPrivateName(member.key)
        ? `#${member.key.id.name}`
        : "property";

      children.push({
        name: propName,
        element_type: "variable",
        source_file: "",
        line_number: member.loc?.start.line || 0,
        end_line_number: member.loc?.end.line || 0,
        docstring: null,
        parameters: [],
        return_type: member.typeAnnotation ? extractTypeAnnotation(member.typeAnnotation) : null,
        is_async: false,
        is_generator: false,
        decorators: [],
        base_classes: [],
        calls: [],
        api_calls: [],
        imports: [],
        inputs: [],
        outputs: [],
        children: [],
      });
    }
  }

  return {
    name: className,
    element_type: "class",
    source_file: "",
    line_number: node.loc?.start.line || 0,
    end_line_number: node.loc?.end.line || 0,
    docstring,
    parameters: [],
    return_type: null,
    is_async: false,
    is_generator: false,
    decorators: [],
    base_classes: baseClasses,
    calls: [],
    api_calls: [],
    imports: [],
    inputs: [],
    outputs: [],
    children,
  };
}

/**
 * Extract call expression information.
 */
function extractCall(node) {
  let name = "";
  let target = null;

  if (t.isIdentifier(node.callee)) {
    name = node.callee.name;
  } else if (t.isMemberExpression(node.callee)) {
    if (t.isIdentifier(node.callee.property)) {
      name = node.callee.property.name;
    }
    if (t.isIdentifier(node.callee.object)) {
      target = node.callee.object.name;
    } else if (t.isMemberExpression(node.callee.object)) {
      target = extractMemberExpression(node.callee.object);
    }
  } else if (t.isCallExpression(node.callee)) {
    // Chained calls like useQuery(...).mutate()
    return extractCall(node.callee);
  }

  if (!name) return null;

  return {
    name,
    target,
    arguments: node.arguments.map((arg) => {
      if (t.isIdentifier(arg)) return arg.name;
      if (t.isStringLiteral(arg)) return `"${arg.value}"`;
      if (t.isNumericLiteral(arg)) return String(arg.value);
      return "...";
    }),
    line_number: node.loc?.start.line || 0,
  };
}

/**
 * Detect API calls (fetch, axios, etc.)
 */
function detectAPICall(node, code) {
  const callee = node.callee;
  let method = "GET";
  let path = null;
  let client = null;

  // fetch('/api/users') or fetch('/api/users', { method: 'POST' })
  if (t.isIdentifier(callee) && callee.name === "fetch") {
    client = "fetch";
    if (node.arguments[0] && t.isStringLiteral(node.arguments[0])) {
      path = node.arguments[0].value;
    } else if (node.arguments[0] && t.isTemplateLiteral(node.arguments[0])) {
      path = extractTemplateLiteral(node.arguments[0]);
    }
    // Check for method in options
    if (node.arguments[1] && t.isObjectExpression(node.arguments[1])) {
      const methodProp = node.arguments[1].properties.find(
        (p) => t.isObjectProperty(p) && t.isIdentifier(p.key) && p.key.name === "method"
      );
      if (methodProp && t.isStringLiteral(methodProp.value)) {
        method = methodProp.value.value.toUpperCase();
      }
    }
  }

  // axios.get('/users'), axios.post('/users', data), etc.
  if (t.isMemberExpression(callee)) {
    const obj = callee.object;
    const prop = callee.property;

    if (t.isIdentifier(obj) && obj.name === "axios" && t.isIdentifier(prop)) {
      client = "axios";
      method = prop.name.toUpperCase();
      if (node.arguments[0] && t.isStringLiteral(node.arguments[0])) {
        path = node.arguments[0].value;
      } else if (node.arguments[0] && t.isTemplateLiteral(node.arguments[0])) {
        path = extractTemplateLiteral(node.arguments[0]);
      }
    }

    // apiClient.get('/users'), api.post('/users'), etc.
    if (
      t.isIdentifier(obj) &&
      (obj.name.toLowerCase().includes("api") || obj.name.toLowerCase().includes("client")) &&
      t.isIdentifier(prop)
    ) {
      const methodNames = ["get", "post", "put", "patch", "delete", "head", "options"];
      if (methodNames.includes(prop.name.toLowerCase())) {
        client = obj.name;
        method = prop.name.toUpperCase();
        if (node.arguments[0] && t.isStringLiteral(node.arguments[0])) {
          path = node.arguments[0].value;
        } else if (node.arguments[0] && t.isTemplateLiteral(node.arguments[0])) {
          path = extractTemplateLiteral(node.arguments[0]);
        }
      }
    }
  }

  // $fetch, useFetch (Nuxt), ky, got, etc.
  if (t.isIdentifier(callee) && ["$fetch", "useFetch", "ky", "got"].includes(callee.name)) {
    client = callee.name;
    if (node.arguments[0] && t.isStringLiteral(node.arguments[0])) {
      path = node.arguments[0].value;
    }
  }

  // React Query / TanStack Query: useQuery, useMutation with queryFn containing API call
  if (t.isIdentifier(callee) && (callee.name === "useQuery" || callee.name === "useMutation" || callee.name === "useInfiniteQuery")) {
    // Look for queryFn or mutationFn in the first argument
    if (node.arguments[0] && t.isObjectExpression(node.arguments[0])) {
      for (const prop of node.arguments[0].properties) {
        if (t.isObjectProperty(prop) && t.isIdentifier(prop.key)) {
          if (prop.key.name === "queryFn" || prop.key.name === "mutationFn") {
            // Extract the function body to find API calls
            const fnNode = prop.value;
            if (t.isArrowFunctionExpression(fnNode) || t.isFunctionExpression(fnNode)) {
              const apiCall = findAPICallInBody(fnNode.body, code);
              if (apiCall) {
                apiCall.client = callee.name;
                return apiCall;
              }
            }
          }
        }
      }
    }
  }

  // SWR: useSWR('/api/users', fetcher)
  if (t.isIdentifier(callee) && callee.name === "useSWR") {
    client = "useSWR";
    if (node.arguments[0] && t.isStringLiteral(node.arguments[0])) {
      path = node.arguments[0].value;
    } else if (node.arguments[0] && t.isTemplateLiteral(node.arguments[0])) {
      path = extractTemplateLiteral(node.arguments[0]);
    }
  }

  // Generic pattern: any function call with URL-like first argument
  if (!path && node.arguments[0]) {
    let potentialPath = null;
    if (t.isStringLiteral(node.arguments[0])) {
      potentialPath = node.arguments[0].value;
    } else if (t.isTemplateLiteral(node.arguments[0])) {
      potentialPath = extractTemplateLiteral(node.arguments[0]);
    }
    // Check if it looks like an API path
    if (potentialPath && (potentialPath.startsWith('/api') || potentialPath.startsWith('/v1') || potentialPath.startsWith('/v2') || potentialPath.match(/^\/[a-z]+\//i))) {
      // Get the function name
      let funcName = null;
      if (t.isIdentifier(callee)) {
        funcName = callee.name;
      } else if (t.isMemberExpression(callee) && t.isIdentifier(callee.property)) {
        funcName = callee.property.name;
      }
      if (funcName) {
        client = funcName;
        path = potentialPath;
        // Infer method from function name
        if (funcName.toLowerCase().includes("post") || funcName.toLowerCase().includes("create")) {
          method = "POST";
        } else if (funcName.toLowerCase().includes("put") || funcName.toLowerCase().includes("update")) {
          method = "PUT";
        } else if (funcName.toLowerCase().includes("delete") || funcName.toLowerCase().includes("remove")) {
          method = "DELETE";
        } else if (funcName.toLowerCase().includes("patch")) {
          method = "PATCH";
        }
      }
    }
  }

  if (path) {
    return {
      method,
      path,
      client,
      line_number: node.loc?.start.line || 0,
      is_external: false,
      matched_endpoint: null,
    };
  }

  return null;
}

/**
 * Find API call inside a function body (for React Query queryFn).
 */
function findAPICallInBody(body, code) {
  let foundApiCall = null;

  const checkNode = (n) => {
    if (!n || typeof n !== "object" || foundApiCall) return;

    if (n.type === "CallExpression") {
      // Try to detect API call in this call expression
      const apiCall = detectAPICallSimple(n);
      if (apiCall) {
        foundApiCall = apiCall;
        return;
      }
    }

    for (const key of Object.keys(n)) {
      const child = n[key];
      if (Array.isArray(child)) {
        for (const item of child) {
          checkNode(item);
        }
      } else if (child && typeof child === "object" && child.type) {
        checkNode(child);
      }
    }
  };

  checkNode(body);
  return foundApiCall;
}

/**
 * Simple API call detection without recursion (to avoid infinite loops in findAPICallInBody).
 */
function detectAPICallSimple(node) {
  const callee = node.callee;
  let method = "GET";
  let path = null;
  let client = null;

  if (t.isMemberExpression(callee)) {
    const obj = callee.object;
    const prop = callee.property;

    // axios.get, api.get, apiClient.post, etc.
    if (t.isIdentifier(obj) && t.isIdentifier(prop)) {
      const methodNames = ["get", "post", "put", "patch", "delete", "head", "options"];
      if (methodNames.includes(prop.name.toLowerCase())) {
        client = obj.name;
        method = prop.name.toUpperCase();
        if (node.arguments[0] && t.isStringLiteral(node.arguments[0])) {
          path = node.arguments[0].value;
        } else if (node.arguments[0] && t.isTemplateLiteral(node.arguments[0])) {
          path = extractTemplateLiteral(node.arguments[0]);
        }
      }
    }
  }

  // fetch()
  if (t.isIdentifier(callee) && callee.name === "fetch") {
    client = "fetch";
    if (node.arguments[0] && t.isStringLiteral(node.arguments[0])) {
      path = node.arguments[0].value;
    } else if (node.arguments[0] && t.isTemplateLiteral(node.arguments[0])) {
      path = extractTemplateLiteral(node.arguments[0]);
    }
  }

  if (path) {
    return { method, path, client, line_number: node.loc?.start.line || 0, is_external: false, matched_endpoint: null };
  }
  return null;
}

/**
 * Traverse function body to extract calls.
 */
function traverseFunctionBody(body, calls, apiCalls, code) {
  const visitor = {
    CallExpression(path) {
      const call = extractCall(path.node);
      if (call) {
        const apiCall = detectAPICall(path.node, code);
        if (apiCall) {
          apiCalls.push(apiCall);
        } else {
          calls.push(call);
        }
      }
    },
  };

  // Simple traversal of the body
  if (t.isBlockStatement(body)) {
    traverseNode(body, visitor);
  } else {
    // Arrow function with expression body
    if (t.isCallExpression(body)) {
      const call = extractCall(body);
      if (call) {
        const apiCall = detectAPICall(body, code);
        if (apiCall) {
          apiCalls.push(apiCall);
        } else {
          calls.push(call);
        }
      }
    }
  }
}

/**
 * Simple node traversal.
 */
function traverseNode(node, visitor) {
  if (!node || typeof node !== "object") return;

  if (node.type === "CallExpression" && visitor.CallExpression) {
    visitor.CallExpression({ node });
  }

  for (const key of Object.keys(node)) {
    const child = node[key];
    if (Array.isArray(child)) {
      for (const item of child) {
        traverseNode(item, visitor);
      }
    } else if (child && typeof child === "object" && child.type) {
      traverseNode(child, visitor);
    }
  }
}

/**
 * Check if a function is a React component.
 */
function detectReactComponent(node) {
  if (!node.body) return false;

  let hasJSXReturn = false;

  const checkNode = (n) => {
    if (!n || typeof n !== "object") return;

    if (n.type === "ReturnStatement" && n.argument) {
      if (n.argument.type === "JSXElement" || n.argument.type === "JSXFragment") {
        hasJSXReturn = true;
      }
    }

    if (n.type === "JSXElement" || n.type === "JSXFragment") {
      hasJSXReturn = true;
    }

    for (const key of Object.keys(n)) {
      const child = n[key];
      if (Array.isArray(child)) {
        for (const item of child) {
          checkNode(item);
        }
      } else if (child && typeof child === "object" && child.type) {
        checkNode(child);
      }
    }
  };

  checkNode(node.body);
  return hasJSXReturn;
}

/**
 * Extract type annotation as string.
 */
function extractTypeAnnotation(typeAnnotation) {
  if (!typeAnnotation) return null;

  const annotation = typeAnnotation.typeAnnotation || typeAnnotation;

  if (t.isTSTypeAnnotation(annotation)) {
    return extractTypeAnnotation(annotation.typeAnnotation);
  }

  if (t.isTSStringKeyword(annotation)) return "string";
  if (t.isTSNumberKeyword(annotation)) return "number";
  if (t.isTSBooleanKeyword(annotation)) return "boolean";
  if (t.isTSAnyKeyword(annotation)) return "any";
  if (t.isTSVoidKeyword(annotation)) return "void";
  if (t.isTSNullKeyword(annotation)) return "null";
  if (t.isTSUndefinedKeyword(annotation)) return "undefined";

  if (t.isTSTypeReference(annotation) && t.isIdentifier(annotation.typeName)) {
    let typeName = annotation.typeName.name;
    if (annotation.typeParameters) {
      const params = annotation.typeParameters.params.map((p) => extractTypeAnnotation(p));
      typeName += `<${params.join(", ")}>`;
    }
    return typeName;
  }

  if (t.isTSArrayType(annotation)) {
    return `${extractTypeAnnotation(annotation.elementType)}[]`;
  }

  if (t.isTSUnionType(annotation)) {
    return annotation.types.map((t) => extractTypeAnnotation(t)).join(" | ");
  }

  if (t.isTSFunctionType(annotation)) {
    return "Function";
  }

  if (t.isTSTypeLiteral(annotation)) {
    return "object";
  }

  return "unknown";
}

/**
 * Extract default value as string.
 */
function extractDefaultValue(node, code) {
  if (t.isStringLiteral(node)) return `"${node.value}"`;
  if (t.isNumericLiteral(node)) return String(node.value);
  if (t.isBooleanLiteral(node)) return String(node.value);
  if (t.isNullLiteral(node)) return "null";
  if (t.isIdentifier(node)) return node.name;
  if (t.isArrayExpression(node)) return "[]";
  if (t.isObjectExpression(node)) return "{}";
  return "...";
}

/**
 * Extract member expression as string.
 */
function extractMemberExpression(node) {
  const parts = [];

  let current = node;
  while (t.isMemberExpression(current)) {
    if (t.isIdentifier(current.property)) {
      parts.unshift(current.property.name);
    }
    current = current.object;
  }

  if (t.isIdentifier(current)) {
    parts.unshift(current.name);
  }

  return parts.join(".");
}

/**
 * Extract template literal as string (with placeholders).
 */
function extractTemplateLiteral(node) {
  let result = "";
  for (let i = 0; i < node.quasis.length; i++) {
    result += node.quasis[i].value.raw;
    if (i < node.expressions.length) {
      const expr = node.expressions[i];
      if (t.isIdentifier(expr)) {
        result += `{${expr.name}}`;
      } else {
        result += "{...}";
      }
    }
  }
  return result;
}

// Main execution
const filePath = process.argv[2];

if (!filePath) {
  console.error("Usage: node parse-ts.js <file_path>");
  process.exit(1);
}

try {
  const result = parseFile(filePath);
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  console.error(JSON.stringify({ error: error.message, stack: error.stack }));
  process.exit(1);
}
