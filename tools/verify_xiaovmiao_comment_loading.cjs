'use strict';
// Exercise the actual functions extracted from the patched frontend bundle.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
async function check(name,next,successful){
 const call=source.indexOf('n.getCall("CommentManager.'+(name==='eU'?'getCommentPostList':'loadPostComment')+'"');
 const start=source.lastIndexOf('function '+name+'(',call),end=source.indexOf('function '+next+'(',call);
 assert.ok(start>=0&&end>start,'Expected frontend request function');
 const changes={posts:[],comments:[],errors:[]};
 const context={h:{platform:'Douyin'},X:0,et:{},eo:{},K:'all',P:{},E:[],R:[],
  eXi:Object.assign,console:{log(){}},Date,
  n:{getCall:()=>successful?Promise.resolve({list:[],nextState:{}}):Promise.reject(Error('fixture permission failure'))},
  j:value=>changes.posts.push(value),H:value=>changes.comments.push(value),
  wZ:{error:message=>changes.errors.push(message)},en(){},N(){},x(){},D(){},ea(){},z(){}};
 vm.createContext(context);vm.runInContext(source.slice(start,end),context);
 await context[name]();
 assert.deepEqual(changes[name==='eU'?'posts':'comments'],[true,false]);
 assert.deepEqual(changes[name==='eU'?'comments':'posts'],[],'Other request loading state must remain independent');
 assert.equal(changes.errors.length,successful?0:1);
}
(async()=>{for(const success of [false,true]){await check('eU','eK',success);await check('eK','eq',success);}console.log('XIAOVMIAO_COMMENT_LOADING_OK');})().catch(error=>{console.error(error.name+': '+error.message);process.exitCode=1;});
