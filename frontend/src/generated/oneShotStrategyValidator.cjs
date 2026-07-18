"use strict";
exports["urn:halpha:strategy:ONE_SHOT_DONCHIAN_ATR_BREAKOUT:parameters:1.0.0"] = validate20;
const schema31 = {"$id":"urn:halpha:strategy:ONE_SHOT_DONCHIAN_ATR_BREAKOUT:parameters:1.0.0","$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false,"allOf":[{"x-halpha-cross-constraint":{"code":"TAKE_PROFIT_ORDER_INVALID","expression":"take_profit_2_r > take_profit_1_r"}}],"properties":{"channel_lookback_15m":{"default":20,"maximum":96,"minimum":20,"type":"integer"},"confirmation_bars_1m":{"default":2,"maximum":3,"minimum":1,"type":"integer"},"direction":{"enum":["LONG","SHORT"],"type":"string"},"entry_valid_minutes":{"default":1440,"maximum":10080,"minimum":15,"type":"integer"},"initial_stop_atr_multiple":{"default":"1.5","pattern":"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$","type":"string","x-halpha-maximum":"3.0","x-halpha-minimum":"1.0"},"max_entry_extension_atr":{"default":"0.5","pattern":"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$","type":"string","x-halpha-maximum":"1.0","x-halpha-minimum":"0.1"},"max_hold_bars_15m":{"default":96,"maximum":672,"minimum":4,"type":"integer"},"take_profit_1_fraction":{"default":"0.50","pattern":"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$","type":"string","x-halpha-maximum":"0.75","x-halpha-minimum":"0.25"},"take_profit_1_r":{"default":"1.5","pattern":"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$","type":"string","x-halpha-maximum":"3.0","x-halpha-minimum":"1.0"},"take_profit_2_r":{"default":"3.0","pattern":"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$","type":"string","x-halpha-maximum":"6.0","x-halpha-minimum":"2.0"}},"required":["direction"],"title":"单次 Donchian 突破与 ATR 风险退出","type":"object"};
const func1 = Object.prototype.hasOwnProperty;
const pattern4 = new RegExp("^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$", "u");

function validate20(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
/*# sourceURL="urn:halpha:strategy:ONE_SHOT_DONCHIAN_ATR_BREAKOUT:parameters:1.0.0" */;
let vErrors = null;
let errors = 0;
const evaluated0 = validate20.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.direction === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "direction"},message:"must have required property '"+"direction"+"'",schema:schema31.required,parentSchema:schema31,data};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
for(const key0 in data){
if(!(func1.call(schema31.properties, key0))){
const err1 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties",schema:false,parentSchema:schema31,data};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
}
if(data.channel_lookback_15m !== undefined){
let data0 = data.channel_lookback_15m;
if(!((typeof data0 == "number") && (!(data0 % 1) && !isNaN(data0)))){
const err2 = {instancePath:instancePath+"/channel_lookback_15m",schemaPath:"#/properties/channel_lookback_15m/type",keyword:"type",params:{type: "integer"},message:"must be integer",schema:schema31.properties.channel_lookback_15m.type,parentSchema:schema31.properties.channel_lookback_15m,data:data0};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(typeof data0 == "number"){
if(data0 > 96 || isNaN(data0)){
const err3 = {instancePath:instancePath+"/channel_lookback_15m",schemaPath:"#/properties/channel_lookback_15m/maximum",keyword:"maximum",params:{comparison: "<=", limit: 96},message:"must be <= 96",schema:96,parentSchema:schema31.properties.channel_lookback_15m,data:data0};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data0 < 20 || isNaN(data0)){
const err4 = {instancePath:instancePath+"/channel_lookback_15m",schemaPath:"#/properties/channel_lookback_15m/minimum",keyword:"minimum",params:{comparison: ">=", limit: 20},message:"must be >= 20",schema:20,parentSchema:schema31.properties.channel_lookback_15m,data:data0};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
}
if(data.confirmation_bars_1m !== undefined){
let data1 = data.confirmation_bars_1m;
if(!((typeof data1 == "number") && (!(data1 % 1) && !isNaN(data1)))){
const err5 = {instancePath:instancePath+"/confirmation_bars_1m",schemaPath:"#/properties/confirmation_bars_1m/type",keyword:"type",params:{type: "integer"},message:"must be integer",schema:schema31.properties.confirmation_bars_1m.type,parentSchema:schema31.properties.confirmation_bars_1m,data:data1};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(typeof data1 == "number"){
if(data1 > 3 || isNaN(data1)){
const err6 = {instancePath:instancePath+"/confirmation_bars_1m",schemaPath:"#/properties/confirmation_bars_1m/maximum",keyword:"maximum",params:{comparison: "<=", limit: 3},message:"must be <= 3",schema:3,parentSchema:schema31.properties.confirmation_bars_1m,data:data1};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data1 < 1 || isNaN(data1)){
const err7 = {instancePath:instancePath+"/confirmation_bars_1m",schemaPath:"#/properties/confirmation_bars_1m/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1",schema:1,parentSchema:schema31.properties.confirmation_bars_1m,data:data1};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
}
if(data.direction !== undefined){
let data2 = data.direction;
if(typeof data2 !== "string"){
const err8 = {instancePath:instancePath+"/direction",schemaPath:"#/properties/direction/type",keyword:"type",params:{type: "string"},message:"must be string",schema:schema31.properties.direction.type,parentSchema:schema31.properties.direction,data:data2};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(!((data2 === "LONG") || (data2 === "SHORT"))){
const err9 = {instancePath:instancePath+"/direction",schemaPath:"#/properties/direction/enum",keyword:"enum",params:{allowedValues: schema31.properties.direction.enum},message:"must be equal to one of the allowed values",schema:schema31.properties.direction.enum,parentSchema:schema31.properties.direction,data:data2};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.entry_valid_minutes !== undefined){
let data3 = data.entry_valid_minutes;
if(!((typeof data3 == "number") && (!(data3 % 1) && !isNaN(data3)))){
const err10 = {instancePath:instancePath+"/entry_valid_minutes",schemaPath:"#/properties/entry_valid_minutes/type",keyword:"type",params:{type: "integer"},message:"must be integer",schema:schema31.properties.entry_valid_minutes.type,parentSchema:schema31.properties.entry_valid_minutes,data:data3};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(typeof data3 == "number"){
if(data3 > 10080 || isNaN(data3)){
const err11 = {instancePath:instancePath+"/entry_valid_minutes",schemaPath:"#/properties/entry_valid_minutes/maximum",keyword:"maximum",params:{comparison: "<=", limit: 10080},message:"must be <= 10080",schema:10080,parentSchema:schema31.properties.entry_valid_minutes,data:data3};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(data3 < 15 || isNaN(data3)){
const err12 = {instancePath:instancePath+"/entry_valid_minutes",schemaPath:"#/properties/entry_valid_minutes/minimum",keyword:"minimum",params:{comparison: ">=", limit: 15},message:"must be >= 15",schema:15,parentSchema:schema31.properties.entry_valid_minutes,data:data3};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
}
if(data.initial_stop_atr_multiple !== undefined){
let data4 = data.initial_stop_atr_multiple;
if(typeof data4 === "string"){
if(!pattern4.test(data4)){
const err13 = {instancePath:instancePath+"/initial_stop_atr_multiple",schemaPath:"#/properties/initial_stop_atr_multiple/pattern",keyword:"pattern",params:{pattern: "^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$"},message:"must match pattern \""+"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$"+"\"",schema:"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$",parentSchema:schema31.properties.initial_stop_atr_multiple,data:data4};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
else {
const err14 = {instancePath:instancePath+"/initial_stop_atr_multiple",schemaPath:"#/properties/initial_stop_atr_multiple/type",keyword:"type",params:{type: "string"},message:"must be string",schema:schema31.properties.initial_stop_atr_multiple.type,parentSchema:schema31.properties.initial_stop_atr_multiple,data:data4};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
if(data.max_entry_extension_atr !== undefined){
let data5 = data.max_entry_extension_atr;
if(typeof data5 === "string"){
if(!pattern4.test(data5)){
const err15 = {instancePath:instancePath+"/max_entry_extension_atr",schemaPath:"#/properties/max_entry_extension_atr/pattern",keyword:"pattern",params:{pattern: "^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$"},message:"must match pattern \""+"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$"+"\"",schema:"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$",parentSchema:schema31.properties.max_entry_extension_atr,data:data5};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
else {
const err16 = {instancePath:instancePath+"/max_entry_extension_atr",schemaPath:"#/properties/max_entry_extension_atr/type",keyword:"type",params:{type: "string"},message:"must be string",schema:schema31.properties.max_entry_extension_atr.type,parentSchema:schema31.properties.max_entry_extension_atr,data:data5};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
if(data.max_hold_bars_15m !== undefined){
let data6 = data.max_hold_bars_15m;
if(!((typeof data6 == "number") && (!(data6 % 1) && !isNaN(data6)))){
const err17 = {instancePath:instancePath+"/max_hold_bars_15m",schemaPath:"#/properties/max_hold_bars_15m/type",keyword:"type",params:{type: "integer"},message:"must be integer",schema:schema31.properties.max_hold_bars_15m.type,parentSchema:schema31.properties.max_hold_bars_15m,data:data6};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
if(typeof data6 == "number"){
if(data6 > 672 || isNaN(data6)){
const err18 = {instancePath:instancePath+"/max_hold_bars_15m",schemaPath:"#/properties/max_hold_bars_15m/maximum",keyword:"maximum",params:{comparison: "<=", limit: 672},message:"must be <= 672",schema:672,parentSchema:schema31.properties.max_hold_bars_15m,data:data6};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
if(data6 < 4 || isNaN(data6)){
const err19 = {instancePath:instancePath+"/max_hold_bars_15m",schemaPath:"#/properties/max_hold_bars_15m/minimum",keyword:"minimum",params:{comparison: ">=", limit: 4},message:"must be >= 4",schema:4,parentSchema:schema31.properties.max_hold_bars_15m,data:data6};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
}
if(data.take_profit_1_fraction !== undefined){
let data7 = data.take_profit_1_fraction;
if(typeof data7 === "string"){
if(!pattern4.test(data7)){
const err20 = {instancePath:instancePath+"/take_profit_1_fraction",schemaPath:"#/properties/take_profit_1_fraction/pattern",keyword:"pattern",params:{pattern: "^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$"},message:"must match pattern \""+"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$"+"\"",schema:"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$",parentSchema:schema31.properties.take_profit_1_fraction,data:data7};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
else {
const err21 = {instancePath:instancePath+"/take_profit_1_fraction",schemaPath:"#/properties/take_profit_1_fraction/type",keyword:"type",params:{type: "string"},message:"must be string",schema:schema31.properties.take_profit_1_fraction.type,parentSchema:schema31.properties.take_profit_1_fraction,data:data7};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data.take_profit_1_r !== undefined){
let data8 = data.take_profit_1_r;
if(typeof data8 === "string"){
if(!pattern4.test(data8)){
const err22 = {instancePath:instancePath+"/take_profit_1_r",schemaPath:"#/properties/take_profit_1_r/pattern",keyword:"pattern",params:{pattern: "^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$"},message:"must match pattern \""+"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$"+"\"",schema:"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$",parentSchema:schema31.properties.take_profit_1_r,data:data8};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
else {
const err23 = {instancePath:instancePath+"/take_profit_1_r",schemaPath:"#/properties/take_profit_1_r/type",keyword:"type",params:{type: "string"},message:"must be string",schema:schema31.properties.take_profit_1_r.type,parentSchema:schema31.properties.take_profit_1_r,data:data8};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data.take_profit_2_r !== undefined){
let data9 = data.take_profit_2_r;
if(typeof data9 === "string"){
if(!pattern4.test(data9)){
const err24 = {instancePath:instancePath+"/take_profit_2_r",schemaPath:"#/properties/take_profit_2_r/pattern",keyword:"pattern",params:{pattern: "^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$"},message:"must match pattern \""+"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$"+"\"",schema:"^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$",parentSchema:schema31.properties.take_profit_2_r,data:data9};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
else {
const err25 = {instancePath:instancePath+"/take_profit_2_r",schemaPath:"#/properties/take_profit_2_r/type",keyword:"type",params:{type: "string"},message:"must be string",schema:schema31.properties.take_profit_2_r.type,parentSchema:schema31.properties.take_profit_2_r,data:data9};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
}
else {
const err26 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object",schema:schema31.type,parentSchema:schema31,data};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
validate20.errors = vErrors;
return errors === 0;
}
validate20.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};
