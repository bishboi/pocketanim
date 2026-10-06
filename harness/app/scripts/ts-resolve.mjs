// Lets node --experimental-strip-types load lib/*.ts that import each other without extensions, as Next does.
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`
export async function resolve(specifier, context, next) {
  try {
    return await next(specifier, context);
  } catch (error) {
    if (specifier.startsWith(".") && !/\\.[a-z]+$/.test(specifier)) return next(specifier + ".ts", context);
    throw error;
  }
}`), import.meta.url);
