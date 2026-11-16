/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean,canceled:boolean,request_key:?string,computation_id:?number,reused_from_job_id:?number}} AnalysisJob */
/** @typedef {{id:number,fingerprint:string,dataset_id:number,epoch:number,status:string,error:string,waiting_jobs:Array,params:Object}} SharedComputation */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
export {};
