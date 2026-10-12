"""Fixed public read queries; no mutations, stream URLs or private fields."""
PROFILE_QUERY = """query($username:String!){
  profileByUsername(username:$username){memberId username}
}"""
TRACKS_QUERY = """query($memberId:String!,$page:Int,$size:Int){
  profileTracks(memberId:$memberId,page:$page,size:$size){
    totalElements totalPages number last
    content{id title v2Id seoMetadata{slug} metadata{tags}
      bundle{hls{duration} stream{duration}} profile{memberId}}
  }
}"""
