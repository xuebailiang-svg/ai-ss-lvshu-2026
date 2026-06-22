import axios from 'axios'; import type {Evaluation,PropertySurvey,Score} from '../types';
export const api=axios.create({baseURL:'/api',timeout:20000});
export const createEvaluation=(data:{name:string;city:string;address:string;radius:number;property:PropertySurvey})=>api.post<Evaluation>('/evaluations',data).then(r=>r.data);
export const listEvaluations=(params?:{city?:string;q?:string})=>api.get<Evaluation[]>('/evaluations',{params}).then(r=>r.data);
export const getEvaluation=(id:string|number)=>api.get<Evaluation>(`/evaluations/${id}`).then(r=>r.data);
export const geocode=(id:number)=>api.post(`/evaluations/${id}/geocode`).then(r=>r.data);
export const collectPois=(id:number)=>api.post(`/evaluations/${id}/collect-pois`).then(r=>r.data);
export const score=(id:number)=>api.post<Score>(`/evaluations/${id}/score`).then(r=>r.data);
export const report=(id:string)=>api.get(`/evaluations/${id}/report`).then(r=>r.data);
