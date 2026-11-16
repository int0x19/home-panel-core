import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const {editDraft, normalizedDraft, roomPlan, editableRoom} = await import(pathToFileURL(process.argv[2]));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const original = JSON.stringify(input.document);
let document = input.document;
const errors = [];
for (const operation of input.operations || []) {
  try { document = editDraft(document, operation, input.capabilities); }
  catch (error) { errors.push(error.code || error.message); }
}
console.log(JSON.stringify({document:normalizedDraft(document), errors,
  unchanged:JSON.stringify(input.document) === original,
  editable:document.rooms.map(room => editableRoom(room, input.capabilities)),
  plans:document.rooms.map(room => roomPlan(document, room, input.capabilities))}));
