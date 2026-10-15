import { readFileSync, writeFileSync } from "node:fs";
import { parseCatalogueContractModel } from "../../../../../frontend-v1/src/catalogue-contract.ts";
const cases=JSON.parse(readFileSync(process.argv[2],"utf8"));
const outputs=[];
for (const c of cases) {
  try { outputs.push({ok:true,value:await parseCatalogueContractModel(c.model,c.value)}); }
  catch(error) { outputs.push({ok:false,error:error.name}); }
}
writeFileSync(process.argv[3],JSON.stringify(outputs));
